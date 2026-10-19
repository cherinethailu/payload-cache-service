"""Service configuration, read from environment variables (prefix ``PAYLOAD_CACHE_``)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PAYLOAD_CACHE_", env_file=".env", extra="ignore")

    # SQLite by default so the service runs with zero infrastructure; any SQLAlchemy URL
    # (e.g. postgresql+psycopg://...) works because only portable SQL is used.
    database_url: str = "sqlite:///./payload_cache.db"

    # Artificial latency of the simulated external transformer. It makes the effect of
    # caching visible when the service is exercised with the CLI.
    transformer_delay_seconds: float = 0.1


@lru_cache
def get_settings() -> Settings:
    return Settings()
