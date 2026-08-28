from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="FUNDER_DEMO_",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str = "sqlite+aiosqlite:///./funder-marketplace.db"
    mcp_token: SecretStr
    ui_token: SecretStr
    operator_token: SecretStr
    execution_token: SecretStr
    event_secret: SecretStr
    host: str = "0.0.0.0"
    port: int = 8093


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

