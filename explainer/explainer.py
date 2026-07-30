"""
Generación de explicaciones legibles de casos de fraude a partir del
detalle de las reglas activadas persistido por el motor de scoring.

Módulo puro: no importa nada de Azure. Recibe el JSON de reglas activadas
(`caso.reglas_activadas_json`) y el score total, y devuelve texto legible.

Las 4 reglas que puede recibir corresponden exactamente a las definidas en
scoring/rules.py — sus IDs y sus campos de `details` son el contrato entre
el motor y este explicador. Si el motor no persistió información suficiente,
se detecta en tiempo de generación (ver _explain_rule) y se documenta en la
explicación en lugar de silenciar el problema.

Requisitos del entregable (Semana3-Azure.md, sección 2.4):
  - Generación determinista mediante plantilla. ✓
  - Correspondencia estricta con las reglas que efectivamente se activaron. ✓
  - Sin modelos de lenguaje generativo. ✓
  - Ejecución asíncrona: el explicador no bloquea la apertura del caso. ✓
  - Si el explicador está caído, los casos se abren sin explicación y se
    explican al restablecerse (garantía del trigger de Service Bus). ✓
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


# IDs de regla — deben coincidir exactamente con scoring/rules.py
RULE_VELOCITY = "velocidad"
RULE_MONTO_ATIPICO = "monto_atipico"
RULE_GEO_IMPOSIBLE = "geo_imposible"
RULE_COMERCIO_RIESGO = "comercio_riesgo"


@dataclass(frozen=True)
class ExplainerInput:
    """Datos mínimos necesarios para generar la explicación de un caso."""

    case_id: str
    transaction_id: str
    score: int
    threshold: int
    rule_activations_json: str  # JSON string tal como está en Caso.reglas_activadas_json

    def parse_activations(self) -> list[dict[str, Any]]:
        return json.loads(self.rule_activations_json)


@dataclass(frozen=True)
class ExplainerOutput:
    """Resultado de la generación: el texto de la explicación y metadatos."""

    case_id: str
    transaction_id: str
    explanation: str
    rules_explained: list[str]   # IDs de reglas incluidas en la explicación
    rules_missing_data: list[str]  # IDs de reglas con datos insuficientes


def _format_amount(minor_units: int | float) -> str:
    """
    Convierte unidades menores (centavos) a formato de moneda legible.
    Se divide por 100 para obtener la unidad mayor y se formatea con
    separador de miles.
    """
    major = round(minor_units / 100)
    return f"${major:,.0f}"


def _explain_velocity(details: dict[str, Any], points: int) -> str:
    count = details.get("transaction_count")
    window_s = details.get("window_seconds")
    max_allowed = details.get("max_allowed")

    if count is None or window_s is None:
        return (
            f"[velocidad +{points} pts] Datos de contexto insuficientes para "
            "generar la explicación de esta regla."
        )

    window_min = window_s // 60
    return (
        f"Se detectaron {count} transacciones de esta cuenta en los últimos "
        f"{window_min} minuto{'s' if window_min != 1 else ''} "
        f"(máximo permitido: {max_allowed}) (+{points} puntos)."
    )


def _explain_monto_atipico(details: dict[str, Any], points: int) -> str:
    observed = details.get("observed_amount_minor_units")
    mean = details.get("historical_mean_minor_units")
    stddev = details.get("historical_stddev_minor_units")
    multiplier = details.get("stddev_multiplier")
    history_size = details.get("history_size")

    if observed is None or mean is None:
        return (
            f"[monto_atipico +{points} pts] Datos de contexto insuficientes para "
            "generar la explicación de esta regla."
        )

    ratio = round(observed / mean, 1) if mean and mean > 0 else None
    ratio_str = f" ({ratio}× el promedio histórico)" if ratio is not None else ""
    mean_str = _format_amount(mean)
    observed_str = _format_amount(observed)
    hist_str = f" (base: {history_size} transacciones)" if history_size else ""

    if stddev is not None and multiplier is not None:
        threshold_str = (
            f"El umbral es media + {multiplier}× desviación estándar "
            f"(σ ≈ {_format_amount(stddev)})."
        )
    else:
        threshold_str = ""

    return (
        f"El monto {observed_str}{ratio_str} supera significativamente el "
        f"promedio histórico de la cuenta ({mean_str}{hist_str}). "
        f"{threshold_str} (+{points} puntos)."
    ).strip()


def _explain_geo_imposible(details: dict[str, Any], points: int) -> str:
    distance_km = details.get("distance_km")
    elapsed_seconds = details.get("elapsed_seconds")
    implied_speed = details.get("implied_speed_kmh")
    max_speed = details.get("max_plausible_speed_kmh")
    prev_tx = details.get("previous_transaction_id")

    if distance_km is None or elapsed_seconds is None:
        return (
            f"[geo_imposible +{points} pts] Datos de contexto insuficientes para "
            "generar la explicación de esta regla."
        )

    elapsed_min = round(elapsed_seconds / 60, 1)

    if implied_speed is None:
        speed_str = "desplazamiento instantáneo (velocidad imposible)"
    else:
        speed_str = f"implica un desplazamiento de {implied_speed:,.0f} km/h"

    prev_str = (
        f" (transacción anterior: {prev_tx[:8]}...)" if prev_tx else ""
    )

    return (
        f"La transacción anterior de esta cuenta ocurrió hace {elapsed_min} min "
        f"a {distance_km:,.1f} km de distancia{prev_str}; "
        f"{speed_str}, por encima del máximo plausible de {max_speed:,.0f} km/h "
        f"(~velocidad de crucero aérea) (+{points} puntos)."
    )


def _explain_comercio_riesgo(details: dict[str, Any], points: int) -> str:
    merchant_id = details.get("merchant_id", "desconocido")
    category = details.get("category", "desconocida")
    by_id = details.get("matched_by_merchant_id", False)
    by_cat = details.get("matched_by_category", False)

    if by_id and by_cat:
        reason = (
            f"el comercio '{merchant_id}' está en la lista de alto riesgo "
            f"y pertenece a la categoría de alto riesgo '{category}'"
        )
    elif by_id:
        reason = f"el comercio '{merchant_id}' está en la lista de comercios de alto riesgo"
    elif by_cat:
        reason = f"la categoría del comercio ('{category}') está marcada como de alto riesgo"
    else:
        reason = f"el comercio '{merchant_id}' (categoría: '{category}') activó una regla de riesgo"

    return f"La transacción fue realizada en {reason} (+{points} puntos)."


_RULE_EXPLAINERS = {
    RULE_VELOCITY: _explain_velocity,
    RULE_MONTO_ATIPICO: _explain_monto_atipico,
    RULE_GEO_IMPOSIBLE: _explain_geo_imposible,
    RULE_COMERCIO_RIESGO: _explain_comercio_riesgo,
}


def generate_explanation(inp: ExplainerInput) -> ExplainerOutput:
    """
    Genera la explicación legible del caso. Determinista: para los mismos
    datos de entrada siempre produce el mismo texto.

    Si alguna regla no tiene datos suficientes para su plantilla, la
    explicación lo indica explícitamente en lugar de omitir la regla o
    inventar datos. La responsabilidad de corregir el registro está en el
    motor de scoring, no en el explicador (Semana3-Azure.md, sección 2.4).
    """
    activations = inp.parse_activations()

    header = (
        f"Transacción marcada con score {inp.score} "
        f"(umbral de apertura de caso: {inp.threshold}).\n"
    )

    if not activations:
        body = (
            "No se registraron reglas activadas para esta transacción. "
            "El motor de scoring no persistió suficiente información; "
            "no es posible generar una explicación detallada."
        )
        return ExplainerOutput(
            case_id=inp.case_id,
            transaction_id=inp.transaction_id,
            explanation=header + "\n" + body,
            rules_explained=[],
            rules_missing_data=[],
        )

    lines = []
    rules_explained = []
    rules_missing_data = []

    for activation in activations:
        rule_id = activation.get("rule_id", "desconocida")
        points = activation.get("points", 0)
        details = activation.get("details", {})

        explainer_fn = _RULE_EXPLAINERS.get(rule_id)
        if explainer_fn is None:
            line = (
                f"[{rule_id} +{points} pts] Regla no reconocida por el explicador. "
                "El motor puede haber añadido una regla nueva no contemplada en esta versión."
            )
            rules_missing_data.append(rule_id)
        else:
            line = explainer_fn(details, points)
            if "Datos de contexto insuficientes" in line:
                rules_missing_data.append(rule_id)
            else:
                rules_explained.append(rule_id)

        lines.append(f"• {line}")

    body = "\n".join(lines)
    explanation = f"{header}\n{body}"

    return ExplainerOutput(
        case_id=inp.case_id,
        transaction_id=inp.transaction_id,
        explanation=explanation,
        rules_explained=rules_explained,
        rules_missing_data=rules_missing_data,
    )
