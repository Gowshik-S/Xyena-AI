from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="LEDGER_DEMO_",
                                      case_sensitive=False, extra="ignore")
    database_url: str = "sqlite+aiosqlite:///./ledger-demo.db"
    mcp_token: SecretStr
    ui_token: SecretStr
    settlement_event_token: SecretStr
    host: str = "0.0.0.0"
    port: int = 8096


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
