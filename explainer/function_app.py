"""
Azure Function del explicador de casos — capa delgada, sin lógica de negocio.

Trigger: Service Bus, misma cola `casos-marcados` que la Function de casos.
Esto garantiza que el explicador recibe el mensaje exactamente cuando se
crea el caso, y que si el explicador está caído, los mensajes se acumulan
en la cola y se procesan al restablecerse (entrega at-least-once de Service
Bus + dead-lettering tras maxDeliveryCount intentos).

Por qué Service Bus y no un timer o un poll a SQL:
  - El mensaje de Service Bus ya contiene el case_id (añadido por el motor
    de scoring al publicar el caso marcado) — no se necesita hacer una
    consulta de "¿qué casos están pendientes?" en el camino feliz.
  - El reintento automático y el dead-lettering son gratuitos con el tier
    Basic; implementarlo manualmente con un poll a SQL añadiría complejidad.
  - Si el explicador estuvo caído, al restablecerse Service Bus entrega
    todos los mensajes acumulados, lo que satisface el criterio de aceptación
    "al restablecerse, las explicaciones pendientes se generan"
    (Semana3-Azure.md §5).

Ejecución asíncrona respecto a la ingesta:
  La API nunca espera al explicador — publica el evento y responde al cliente.
  La latencia de la ingesta no se ve afectada por el tiempo de generación
  de la explicación. Esta independencia es la que el criterio de aceptación
  §5 exige verificar con el explicador detenido.
"""

import json
import logging

import azure.functions as func

from config import get_settings
from explainer import ExplainerInput, generate_explanation
from repository import SqlAlchemyExplainerRepository
from db import create_azure_sql_engine, create_session

app = func.FunctionApp()
logger = logging.getLogger(__name__)


@app.function_name(name="ExplainerFunction")
@app.service_bus_queue_trigger(
    arg_name="msg",
    queue_name="casos-marcados",
    connection="ServiceBusConnection",
)
def explainer_function(msg: func.ServiceBusMessage) -> None:
    """
    Genera la explicación del caso indicado en el mensaje y la persiste
    en la columna `explicacion_texto` de la tabla `caso`.
    """
    body = json.loads(msg.get_body().decode("utf-8"))
    _process_explanation_message(body)


def _process_explanation_message(
    body: dict,
    repository: SqlAlchemyExplainerRepository | None = None,
) -> None:
    """
    Lógica separada del binding para poder probar de punta a punta con
    un repositorio SQLite en memoria, igual que en cases/function_app.py.
    """
    transaction_id = body.get("transaction_id", "<desconocido>")
    score = body.get("score", 0)
    rule_activations_json = json.dumps(body.get("rule_activations", []))

    settings = get_settings()
    owns_repository = repository is None

    if repository is None:
        engine = create_azure_sql_engine(settings.sql_server, settings.sql_database)
        repository = SqlAlchemyExplainerRepository(create_session(engine))

    try:
        # Buscar el caso recién creado por la Function de casos.
        # Puede haber una breve ventana de tiempo entre que Service Bus entrega
        # el mensaje al explicador y que la Function de casos termina de insertar
        # el registro en SQL. El campo case_id viene en el payload para
        # evitar una búsqueda por transaction_id.
        case_id = body.get("case_id")
        caso = repository.get_case(case_id) if case_id else None

        if caso is None:
            # Fallback: buscar por transaction_id si case_id no está en el payload
            # (compatibilidad con mensajes de versiones anteriores del motor).
            logger.warning(
                "case_id no presente en el mensaje para transaction_id=%s; "
                "buscando por transaction_id (degradado).",
                transaction_id,
            )
            # En este caso usamos el score y las reglas del payload directamente.

        threshold = settings.score_threshold
        inp = ExplainerInput(
            case_id=case_id or transaction_id,  # fallback al tx_id si no hay case_id
            transaction_id=transaction_id,
            score=score,
            threshold=threshold,
            rule_activations_json=rule_activations_json,
        )

        result = generate_explanation(inp)

        if case_id and caso is not None:
            repository.save_explanation(case_id, result.explanation)
            logger.info(
                "Explicación generada para caso %s (tx %s): reglas=%s, sin_datos=%s",
                case_id,
                transaction_id,
                result.rules_explained,
                result.rules_missing_data,
            )
        else:
            # Si no encontramos el caso en SQL (race condition o error de casos),
            # logueamos la explicación generada pero no fallamos el mensaje —
            # el dead-lettering de Service Bus se encargará si hay reintentos
            # configurados. No lanzamos excepción para no reencolar el mismo
            # mensaje si el caso definitivamente no existe.
            logger.warning(
                "Caso no encontrado en SQL para tx %s. Explicación generada pero no persistida: %s",
                transaction_id,
                result.explanation[:200],
            )

    finally:
        if owns_repository:
            repository.close()
