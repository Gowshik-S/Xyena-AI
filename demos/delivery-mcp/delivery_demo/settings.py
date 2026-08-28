from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="DELIVERY_DEMO_",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str = "sqlite+aiosqlite:///./delivery-demo.db"
    mcp_token: SecretStr
    source_signing_key: SecretStr
    event_signing_key: SecretStr
    viewer_token: SecretStr
    seller_token: SecretStr
    carrier_token: SecretStr
    buyer_token: SecretStr
    reviewer_token: SecretStr
    admin_token: SecretStr
    host: str = "0.0.0.0"
    port: int = 8095


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
