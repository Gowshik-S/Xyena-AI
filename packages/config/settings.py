from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, Field, SecretStr, field_validator
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
    openai_embedding_model: str = "text-embedding-3-small"
    model_provider: Literal["openai", "command_code", "nvidia_nim"] = "openai"
    command_code_api_key: SecretStr | None = None
    command_code_base_url: AnyHttpUrl = "https://api.commandcode.ai/provider/v1"
    command_code_zdr: bool = True
    nvidia_nim_api_key: SecretStr | None = None
    nvidia_nim_api_keys: SecretStr | None = None
    nvidia_nim_base_url: AnyHttpUrl = "https://integrate.api.nvidia.com/v1"

    oidc_issuer: str = "https://identity.example.com"
    oidc_audience: str = "xyena-api"
    oidc_jwks_url: str | None = None
    dev_auth_bypass: bool = False
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    guardian_base_url: AnyHttpUrl = "http://guardian:8082"
    mcp_base_url: AnyHttpUrl = "http://mcp-server:8081"
    service_token: SecretStr | None = None
    mcp_admin_token: SecretStr | None = None
    guardian_signing_key: SecretStr | None = None
    guardian_verify_key: SecretStr | None = None

    object_store_endpoint: str | None = None
    object_store_bucket: str = "xyena-artifacts"
    object_store_access_key: SecretStr | None = None
    object_store_secret_key: SecretStr | None = None
    object_store_region: str = "us-east-1"

    otel_service_namespace: str = "xyena"
    otel_exporter_otlp_endpoint: str | None = None
    event_webhook_url: AnyHttpUrl | None = None

    api_host: str = "0.0.0.0"
    api_port: int = 8080
    mcp_port: int = 8081
    guardian_port: int = 8082
    worker_poll_seconds: float = 1.0
    run_event_poll_seconds: float = 0.5

    @field_validator(
        "openai_api_key",
        "command_code_api_key",
        "nvidia_nim_api_key",
        "nvidia_nim_api_keys",
        "service_token",
        "mcp_admin_token",
        "guardian_signing_key",
        "guardian_verify_key",
        "object_store_access_key",
        "object_store_secret_key",
        "event_webhook_url",
        mode="before",
    )
    @classmethod
    def blank_optional_values_are_none(cls, value: object) -> object | None:
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        return value

    @property
    def jwks_url(self) -> str:
        return self.oidc_jwks_url or f"{self.oidc_issuer.rstrip('/')}/.well-known/jwks.json"

    @property
    def model_api_key(self) -> SecretStr | None:
        if self.model_provider == "command_code":
            return self.command_code_api_key
        if self.model_provider == "nvidia_nim":
            return self.nvidia_nim_api_keys or self.nvidia_nim_api_key
        return self.openai_api_key

    @property
    def nvidia_nim_keys(self) -> tuple[str, ...]:
        configured = self.nvidia_nim_api_keys or self.nvidia_nim_api_key
        if configured is None:
            return ()
        keys = (value.strip() for value in configured.get_secret_value().split(","))
        return tuple(dict.fromkeys(value for value in keys if value))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
