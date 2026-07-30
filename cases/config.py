from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CENTINELA_CASES_", env_file=".env", extra="ignore")

    # p. ej. 'sql-trial-dev-weu-003.database.windows.net'
    sql_server: str
    sql_database: str = "centinela-casos"


@lru_cache
def get_settings() -> Settings:
    return Settings()
