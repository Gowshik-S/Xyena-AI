from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="REGISTRY_DEMO_",
        case_sensitive=False,
        extra="ignore",
    )

    env: str = "development"
    database_url: str = "sqlite+aiosqlite:///./business-registry.db"
    mcp_token: SecretStr
    operator_password: SecretStr
    reviewer_password: SecretStr
    cookie_secure: bool = False
    host: str = "0.0.0.0"
    port: int = 8093


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
