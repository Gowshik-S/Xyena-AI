from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="GST_PORTAL_",
        case_sensitive=False,
        extra="ignore",
    )

    env: str = "development"
    database_url: str = "sqlite+aiosqlite:///./gst-portal.db"
    mcp_token: SecretStr
    demo_password: SecretStr
    cookie_secure: bool = False
    host: str = "0.0.0.0"
    port: int = 8091


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
