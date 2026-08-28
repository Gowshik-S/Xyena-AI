"""Create the EC2 deployment environment without printing any generated secret."""

from __future__ import annotations

import argparse
import os
import secrets
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / ".env"


def token(size: int = 32) -> str:
    return secrets.token_hex(size)


def guardian_keys() -> tuple[str, str]:
    with tempfile.TemporaryDirectory() as temporary_directory:
        private_path = Path(temporary_directory) / "guardian-private.pem"
        subprocess.run(
            ["openssl", "genpkey", "-algorithm", "Ed25519", "-out", str(private_path)],
            check=True,
            capture_output=True,
        )
        public = subprocess.run(
            ["openssl", "pkey", "-in", str(private_path), "-pubout"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        private = private_path.read_text(encoding="utf-8")
    return private.replace("\n", "\\n"), public.replace("\n", "\\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="replace an existing .env")
    args = parser.parse_args()
    if OUTPUT.exists() and not args.force:
        raise SystemExit(f"{OUTPUT} already exists; refusing to rotate deployment secrets")

    postgres_password = token()
    minio_password = token()
    service_token = token()
    mcp_admin_token = token()
    bank_mcp_token = token()
    gst_mcp_token = token()
    erp_mcp_token = token()
    registry_mcp_token = token()
    funder_mcp_token = token()
    delivery_mcp_token = token()
    ledger_mcp_token = token()
    gst_event_secret = token()
    guardian_signing_key, guardian_verify_key = guardian_keys()

    values = {
        "POSTGRES_PASSWORD": postgres_password,
        "BANK_DB_PASSWORD": token(),
        "GST_DB_PASSWORD": token(),
        "ERP_DB_PASSWORD": token(),
        "REGISTRY_DB_PASSWORD": token(),
        "FUNDER_DB_PASSWORD": token(),
        "DELIVERY_DB_PASSWORD": token(),
        "LEDGER_DB_PASSWORD": token(),
        "MINIO_ROOT_USER": "xyena-platform",
        "MINIO_ROOT_PASSWORD": minio_password,
        "XYENA_ENV": "production",
        "XYENA_LOG_LEVEL": "INFO",
        "XYENA_DATABASE_URL": f"postgresql+psycopg://xyena:{postgres_password}@postgres:5432/xyena",
        "XYENA_REDIS_URL": "redis://redis:6379/0",
        "XYENA_OPENAI_API_KEY": os.getenv("OPENAI_API_KEY", ""),
        "XYENA_OPENAI_MODEL": "gpt-5.6-terra",
        "XYENA_OPENAI_EMBEDDING_MODEL": "text-embedding-3-small",
        "XYENA_OIDC_ISSUER": "https://identity.gowshik.in",
        "XYENA_OIDC_AUDIENCE": "xyena-api",
        "XYENA_OIDC_JWKS_URL": "",
        "XYENA_DEV_AUTH_BYPASS": "false",
        "XYENA_CORS_ORIGINS": '["https://app.gowshik.in"]',
        "XYENA_GUARDIAN_BASE_URL": "http://guardian:8082",
        "XYENA_MCP_BASE_URL": "http://mcp-server:8081",
        "XYENA_SERVICE_TOKEN": service_token,
        "XYENA_MCP_ADMIN_TOKEN": mcp_admin_token,
        "XYENA_GUARDIAN_SIGNING_KEY": guardian_signing_key,
        "XYENA_GUARDIAN_VERIFY_KEY": guardian_verify_key,
        "XYENA_OBJECT_STORE_ENDPOINT": "http://minio:9000",
        "XYENA_OBJECT_STORE_BUCKET": "xyena-artifacts",
        "XYENA_OBJECT_STORE_ACCESS_KEY": "xyena-platform",
        "XYENA_OBJECT_STORE_SECRET_KEY": minio_password,
        "XYENA_OBJECT_STORE_REGION": "us-east-1",
        "XYENA_OTEL_SERVICE_NAMESPACE": "xyena",
        "XYENA_OTEL_EXPORTER_OTLP_ENDPOINT": "",
        "XYENA_EVENT_WEBHOOK_URL": "",
        "XYENA_MCP_CONTROL_URL": "http://mcp-server:8081",
        "BANK_DEMO_DATABASE_URL": "postgresql+asyncpg://bank_app:${BANK_DB_PASSWORD}@postgres:5432/bank_demo",
        "BANK_DEMO_MCP_TOKEN": bank_mcp_token,
        "BANK_DEMO_UI_TOKEN": token(),
        "BANK_DEMO_HOST": "0.0.0.0",
        "BANK_DEMO_PORT": "8090",
        "BANK_DEMO_PUBLIC_MCP_URL": "http://bank-demo:8090/mcp",
        "BANK_DEMO_TENANT_ID": "00000000-0000-4000-8000-000000000101",
        "GST_PORTAL_ENV": "production",
        "GST_PORTAL_DATABASE_URL": "postgresql+asyncpg://gst_app:${GST_DB_PASSWORD}@postgres:5432/gst_demo",
        "GST_PORTAL_MCP_TOKEN": gst_mcp_token,
        "GST_PORTAL_DEMO_PASSWORD": token(12),
        "GST_PORTAL_COOKIE_SECURE": "true",
        "GST_PORTAL_HOST": "0.0.0.0",
        "GST_PORTAL_PORT": "8091",
        "GST_PORTAL_PUBLIC_MCP_URL": "http://gst-portal:8091/mcp",
        "GST_PORTAL_TENANT_IDS": "00000000-0000-4000-8000-000000001101,00000000-0000-4000-8000-000000001102,00000000-0000-4000-8000-000000001103",
        "ERP_DEMO_DATABASE_URL": "postgresql+asyncpg://erp_app:${ERP_DB_PASSWORD}@postgres:5432/erp_demo",
        "ERP_DEMO_MCP_TOKEN": erp_mcp_token,
        "BUYER_ERP_MCP_TOKEN": erp_mcp_token,
        "ERP_DEMO_UI_TOKEN": token(),
        "ERP_DEMO_ADMIN_TOKEN": token(),
        "ERP_DEMO_GST_EVENT_SECRET": gst_event_secret,
        "ERP_DEMO_GST_BASE_URL": "",
        "ERP_DEMO_GST_SERVICE_TOKEN": "",
        "ERP_DEMO_HOST": "0.0.0.0",
        "ERP_DEMO_PORT": "8092",
        "ERP_DEMO_PUBLIC_MCP_URL": "http://buyer-erp:8092/mcp",
        "ERP_DEMO_TENANT_ID": "00000000-0000-4000-8000-000000000101",
        "REGISTRY_DEMO_ENV": "production",
        "REGISTRY_DEMO_DATABASE_URL": "postgresql+asyncpg://registry_app:${REGISTRY_DB_PASSWORD}@postgres:5432/registry_demo",
        "REGISTRY_DEMO_MCP_TOKEN": registry_mcp_token,
        "REGISTRY_DEMO_OPERATOR_PASSWORD": token(12),
        "REGISTRY_DEMO_REVIEWER_PASSWORD": token(12),
        "REGISTRY_DEMO_COOKIE_SECURE": "true",
        "REGISTRY_DEMO_HOST": "0.0.0.0",
        "REGISTRY_DEMO_PORT": "8093",
        "REGISTRY_DEMO_PUBLIC_MCP_URL": "http://business-registry:8093/mcp",
        "REGISTRY_DEMO_TENANT_IDS": "00000000-0000-4000-8000-000000001301",
        "FUNDER_DEMO_DATABASE_URL": "postgresql+asyncpg://funder_app:${FUNDER_DB_PASSWORD}@postgres:5432/funder_demo",
        "FUNDER_DEMO_MCP_TOKEN": funder_mcp_token,
        "FUNDER_MARKETPLACE_MCP_TOKEN": funder_mcp_token,
        "FUNDER_DEMO_UI_TOKEN": token(),
        "FUNDER_DEMO_OPERATOR_TOKEN": token(),
        "FUNDER_DEMO_EXECUTION_TOKEN": token(),
        "FUNDER_DEMO_EVENT_SECRET": token(),
        "FUNDER_DEMO_HOST": "0.0.0.0",
        "FUNDER_DEMO_PORT": "8094",
        "FUNDER_DEMO_PUBLIC_MCP_URL": "http://funder-marketplace:8094/mcp",
        "FUNDER_DEMO_TENANT_ID": "00000000-0000-4000-8000-000000000101",
        "DELIVERY_DEMO_DATABASE_URL": "postgresql+asyncpg://delivery_app:${DELIVERY_DB_PASSWORD}@postgres:5432/delivery_demo",
        "DELIVERY_DEMO_MCP_TOKEN": delivery_mcp_token,
        "DELIVERY_DEMO_SOURCE_SIGNING_KEY": token(),
        "DELIVERY_DEMO_EVENT_SIGNING_KEY": token(),
        "DELIVERY_DEMO_VIEWER_TOKEN": token(),
        "DELIVERY_DEMO_SELLER_TOKEN": token(),
        "DELIVERY_DEMO_CARRIER_TOKEN": token(),
        "DELIVERY_DEMO_BUYER_TOKEN": token(),
        "DELIVERY_DEMO_REVIEWER_TOKEN": token(),
        "DELIVERY_DEMO_ADMIN_TOKEN": token(),
        "DELIVERY_DEMO_HOST": "0.0.0.0",
        "DELIVERY_DEMO_PORT": "8095",
        "DELIVERY_DEMO_PUBLIC_MCP_URL": "http://delivery-demo:8095/mcp",
        "DELIVERY_DEMO_TENANT_ID": "00000000-0000-4000-8000-000000000101",
        "LEDGER_DEMO_DATABASE_URL": "postgresql+asyncpg://ledger_app:${LEDGER_DB_PASSWORD}@postgres:5432/ledger_demo",
        "LEDGER_DEMO_MCP_TOKEN": ledger_mcp_token,
        "LEDGER_DEMO_UI_TOKEN": token(),
        "LEDGER_DEMO_SETTLEMENT_EVENT_TOKEN": token(),
        "LEDGER_DEMO_HOST": "0.0.0.0",
        "LEDGER_DEMO_PORT": "8096",
        "LEDGER_DEMO_PUBLIC_MCP_URL": "http://ledger-payment:8096/mcp",
        "LEDGER_DEMO_TENANT_ID": "00000000-0000-4000-8000-000000000101",
    }

    OUTPUT.write_text(
        "\n".join(f"{name}={value}" for name, value in values.items()) + "\n",
        encoding="utf-8",
    )
    OUTPUT.chmod(0o600)
    print(f"Created {OUTPUT} with mode 0600. No secrets were printed.")


if __name__ == "__main__":
    main()
