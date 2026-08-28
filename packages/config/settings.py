from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="XYENA_",
        case_sensitive=False,
        extra="ignore",
    )

    env: Literal["development", "test", "staging", "production"] = "development"
    log_level: str = "INFO"
    database_url: str = "postgresql+psycopg://xyena:xyena@localhost:5432/xyena"
    redis_url: str = "redis://localhost:6379/0"

    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-5.6-terra"

    oidc_issuer: str = "https://identity.example.com"
    oidc_audience: str = "xyena-api"
    oidc_jwks_url: str | None = None
    dev_auth_bypass: bool = False
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    guardian_base_url: AnyHttpUrl = "http://guardian:8082"
    mcp_base_url: AnyHttpUrl = "http://mcp-server:8081"
    service_token: SecretStr | None = None
    guardian_signing_key: SecretStr | None = None
    guardian_verify_key: SecretStr | None = None

    object_store_endpoint: str | None = None
    object_store_bucket: str = "xyena-artifacts"
    object_store_access_key: SecretStr | None = None
    object_store_secret_key: SecretStr | None = None

    api_host: str = "0.0.0.0"
    api_port: int = 8080
    mcp_port: int = 8081
    guardian_port: int = 8082
    worker_poll_seconds: float = 1.0
    run_event_poll_seconds: float = 0.5

    @property
    def jwks_url(self) -> str:
        return self.oidc_jwks_url or f"{self.oidc_issuer.rstrip('/')}/.well-known/jwks.json"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

