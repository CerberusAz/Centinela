"""
Configuración del explicador — leída de variables de entorno (App Settings
de Azure) en tiempo de ejecución. Sin valores por defecto para los
secretos/endpoints: si no están configurados, el arranque falla de forma
explícita en lugar de silenciosa.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings


class ExplainerSettings(BaseSettings):
    # Azure SQL — mismo patrón que cases/config.py
    sql_server: str  # FQDN del servidor: sql-trial-dev-cus-003.database.windows.net
    sql_database: str

    # Score threshold — debe coincidir con el del motor de scoring para que
    # la explicación cite el umbral correcto. Se lee de App Settings para
    # poder cambiarlo sin redespliegue, igual que en el motor.
    score_threshold: int = 100

    model_config = {"env_prefix": "CENTINELA_EXPLAINER_"}


@lru_cache(maxsize=1)
def get_settings() -> ExplainerSettings:
    return ExplainerSettings()
