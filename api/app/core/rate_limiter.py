"""
Limitación de tasa de la API de ingesta (Azure-Semana2.md, sección 2.7):
"La API de ingesta está expuesta a internet. Debe implementarse una
limitación de tasa que restrinja el número de peticiones aceptadas por
origen en una ventana temporal." La sección 2.7 también aclara que el
proyecto no contempla una capa de gestión de API dedicada — se implementa
en la aplicación, que es exactamente lo que hace este módulo.

Ventana deslizante en memoria por IP de origen. Limitación conocida y
documentada en docs/limite-tasa-api.md: en memoria significa por-instancia
del proceso — con una sola instancia de App Service (Plan B1, sin
auto-escalado esta semana) el conteo es exacto; si se escala a varias
instancias, cada una contaría por separado y el límite efectivo real
sería `max_requests × número_de_instancias`. No es un defecto de este
código, es una propiedad conocida de un limitador sin estado compartido —
resolverlo requeriría un almacén centralizado (p. ej. la misma cuenta de
Storage vía tablas, o Redis), fuera de alcance de esta semana.
"""

import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Callable

from fastapi import Depends, HTTPException, Request, status

from app.core.config import Settings, get_settings


@dataclass(frozen=True)
class RateLimitConfig:
    window_seconds: int
    max_requests: int


class InMemoryRateLimiter:
    """
    Ventana deslizante: por cada identificador de cliente, se guardan las
    marcas de tiempo de sus peticiones dentro de la ventana vigente. Una
    petición se permite si, tras descartar las marcas fuera de ventana,
    quedan menos de `max_requests` registradas.

    El reloj es inyectable (`clock`) para poder probar el comportamiento
    de la ventana sin depender de `time.sleep()` real en los tests.
    """

    def __init__(
        self, config: RateLimitConfig, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._config = config
        self._clock = clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, client_id: str) -> None:
        now = self._clock()
        window_start = now - self._config.window_seconds
        hits = self._hits[client_id]

        while hits and hits[0] < window_start:
            hits.popleft()

        if len(hits) >= self._config.max_requests:
            oldest = hits[0]
            retry_after = max(1, int(self._config.window_seconds - (now - oldest)) + 1)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Límite de peticiones excedido. Intente de nuevo más tarde.",
                headers={"Retry-After": str(retry_after)},
            )

        hits.append(now)


_limiter_instance: InMemoryRateLimiter | None = None


def get_rate_limiter(settings: Settings = Depends(get_settings)) -> InMemoryRateLimiter:
    global _limiter_instance
    if _limiter_instance is None:
        _limiter_instance = InMemoryRateLimiter(
            RateLimitConfig(
                window_seconds=settings.rate_limit_window_seconds,
                max_requests=settings.rate_limit_max_requests,
            )
        )
    return _limiter_instance


def _client_identifier(request: Request) -> str:
    """
    Prioriza `X-Forwarded-For` (el proxy de Azure App Service expone ahí
    la IP real del cliente; `request.client.host` en producción sería la
    IP del balanceador interno, no la del origen real) y cae de vuelta a
    `request.client.host` para ejecución local sin proxy delante.
    """
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def enforce_rate_limit(
    request: Request,
    limiter: InMemoryRateLimiter = Depends(get_rate_limiter),
) -> None:
    limiter.check(_client_identifier(request))
