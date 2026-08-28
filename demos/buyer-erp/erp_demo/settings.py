from functools import lru_cache

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="ERP_DEMO_",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str = "sqlite+aiosqlite:///./buyer-erp.db"
    mcp_token: SecretStr
    ui_token: SecretStr
    admin_token: SecretStr
    gst_event_secret: SecretStr
    gst_base_url: str | None = None
    gst_service_token: SecretStr | None = None
    host: str = "0.0.0.0"
    port: int = 8092

    @field_validator("gst_base_url", "gst_service_token", mode="before")
    @classmethod
    def blank_optional_values_are_none(cls, value: object) -> object | None:
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
