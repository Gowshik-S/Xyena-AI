import asyncio
import os
from typing import Any
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv

load_dotenv()

POLICIES: dict[str, dict[str, Any]] = {
    "ledger.accounts.get_balance": {"risk_class": "SENSITIVE_READ", "side_effects": False},
    "ledger.journals.get": {"risk_class": "SENSITIVE_READ", "side_effects": False},
    "ledger.payments.get_status": {"risk_class": "SENSITIVE_READ", "side_effects": False},
    "ledger.reconciliation.get": {"risk_class": "SENSITIVE_READ", "side_effects": False},
    "ledger.disbursements.prepare": {"risk_class": "MUTATE", "side_effects": True},
    "ledger.disbursements.execute": {"risk_class": "PRIVILEGED", "side_effects": True, "approval_mode": "ALWAYS"},
    "ledger.reversals.prepare": {"risk_class": "MUTATE", "side_effects": True},
    "ledger.reversals.execute": {"risk_class": "PRIVILEGED", "side_effects": True, "approval_mode": "ALWAYS"},
}


def required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} must be configured.")
    return value


async def register() -> None:
    control_url = required("XYENA_MCP_CONTROL_URL").rstrip("/")
    service_headers = {"Authorization": f"Bearer {required('XYENA_SERVICE_TOKEN')}"}
    review_headers = {"X-MCP-Admin-Token": required("XYENA_MCP_ADMIN_TOKEN")}
    public_url, tenant_id = required("LEDGER_DEMO_PUBLIC_MCP_URL"), required("LEDGER_DEMO_TENANT_ID")
    hostname = urlparse(public_url).hostname
    if not hostname:
        raise RuntimeError("LEDGER_DEMO_PUBLIC_MCP_URL must include a hostname.")
    params = {"tenant_id": tenant_id}
    async with httpx.AsyncClient(base_url=control_url, timeout=90) as client:
        response = await client.get("/internal/mcp/servers", params=params, headers=service_headers)
        response.raise_for_status()
        server = next((item for item in response.json() if item["label"] == "ledger"), None)
        if server is None:
            response = await client.post("/internal/mcp/servers", params=params, headers=service_headers,
                json={"label": "ledger", "description": "XYENA double-entry ledger and payment operations",
                      "transport": "STREAMABLE_HTTP", "endpoint": public_url,
                      "auth_type": "BEARER", "secret_ref": "env://LEDGER_DEMO_MCP_TOKEN",
                      "trust_tier": "UNREVIEWED", "allowed_egress_hosts": [hostname],
                      "timeout_seconds": 30, "max_retries": 0})
            response.raise_for_status(); server = response.json()
        elif server["endpoint"].rstrip("/") != public_url.rstrip("/"):
            raise RuntimeError("The ledger label already uses another endpoint.")
        server_id = server["id"]
        response = await client.post(f"/internal/mcp/servers/{server_id}/discover",
                                     params=params, headers=service_headers); response.raise_for_status()
        response = await client.post(f"/internal/mcp/servers/{server_id}/review", params=params,
                                     headers=review_headers,
                                     json={"trust_tier": "REVIEWED_INTERNAL", "status": "ACTIVE"}); response.raise_for_status()
        response = await client.get(f"/internal/mcp/servers/{server_id}/tools",
                                    params=params, headers=review_headers); response.raise_for_status()
        latest: dict[str, dict[str, Any]] = {}
        for tool in response.json():
            latest.setdefault(tool["canonical_name"], tool)
        if set(latest) != set(POLICIES):
            raise RuntimeError(f"Ledger discovery mismatch: expected={sorted(POLICIES)} actual={sorted(latest)}")
        for name, policy in POLICIES.items():
            response = await client.post(f"/internal/mcp/tools/{latest[name]['tool_version_id']}/review",
                params=params, headers=review_headers,
                json={"canonical_name": name, "risk_class": policy["risk_class"],
                      "required_roles": [], "required_purposes": [], "required_consents": [],
                      "allowed_agents": ["xyena-supervisor"],
                      "approval_mode": policy.get("approval_mode", "POLICY"),
                      "side_effects": policy["side_effects"], "idempotent": True,
                      "parallel_allowed": False, "hosted_mcp_allowed": False,
                      "timeout_seconds": 30, "maximum_result_bytes": 131072})
            response.raise_for_status()
    print(f"Activated {len(POLICIES)} reviewed ledger tools on MCP server {server_id}.")


def main() -> None:
    asyncio.run(register())


if __name__ == "__main__":
    main()
