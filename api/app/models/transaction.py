import re
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, field_validator

_UUID4_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
_CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")


class Location(BaseModel):
    """Representación que permite el cálculo de distancia (regla geo-imposible)."""

    model_config = ConfigDict(extra="forbid")

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class Merchant(BaseModel):
    model_config = ConfigDict(extra="forbid")

    merchant_id: str = Field(min_length=1, max_length=64)
    category: str = Field(min_length=1, max_length=64)


class TransactionIn(BaseModel):
    """
    Contrato de la transacción (Azure-Semana1.md, sección 2.8). Ver
    docs/contrato-transaccion.md para las cuatro decisiones justificadas
    (marca de tiempo, monto, ubicación, identificador).

    extra="forbid": un campo no contemplado en el contrato se rechaza
    (política decidida por la célula, documentada en docs/contrato-transaccion.md).
    """

    model_config = ConfigDict(extra="forbid")

    transaction_id: str = Field(
        description=(
            "UUID v4 generado por el sistema de origen (canal/cliente que emite "
            "la transacción), no por el servidor. Actúa como clave de idempotencia."
        )
    )
    account_id: str = Field(min_length=1, max_length=128, description="¿De qué cuenta proviene?")
    amount_minor_units: int = Field(
        gt=0,
        description=(
            "Monto en la unidad monetaria menor (p. ej. centavos) para evitar "
            "los errores de representación de coma flotante en valores monetarios."
        ),
    )
    currency: str = Field(description="Código de moneda ISO 4217, p. ej. USD.")
    client_timestamp: datetime = Field(
        description=(
            "Instante declarado por el sistema de origen. Es informativo, no "
            "autoritativo: la API asigna además server_received_at al persistir, "
            "y las reglas de velocidad/geo-imposible de la semana 2 deben usar "
            "ese valor, no este."
        )
    )
    location: Location = Field(description="¿Desde qué ubicación se originó?")
    merchant: Merchant = Field(description="¿Hacia qué comercio o categoría se dirige?")

    @field_validator("transaction_id")
    @classmethod
    def _validate_transaction_id(cls, value: str) -> str:
        if not _UUID4_PATTERN.match(value):
            raise ValueError("transaction_id debe ser un UUID v4")
        return value.lower()

    @field_validator("currency")
    @classmethod
    def _validate_currency(cls, value: str) -> str:
        if not _CURRENCY_PATTERN.match(value):
            raise ValueError("currency debe ser un código ISO 4217 de 3 letras mayúsculas")
        return value

    @field_validator("client_timestamp")
    @classmethod
    def _validate_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("client_timestamp debe incluir zona horaria (UTC recomendado)")
        return value.astimezone(timezone.utc)
