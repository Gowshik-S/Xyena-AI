import asyncio
import os
from typing import Any
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv


load_dotenv()

TOOL_POLICIES: dict[str, dict[str, Any]] = {
    "funder.programs.search": {"risk_class": "SENSITIVE_READ", "side_effects": False, "idempotent": True},
    "funder.offers.request": {"risk_class": "MUTATE", "side_effects": True, "idempotent": False},
    "funder.offers.get": {"risk_class": "SENSITIVE_READ", "side_effects": False, "idempotent": True},
    "funder.offers.reserve": {"risk_class": "PRIVILEGED", "side_effects": True, "idempotent": True},
    "funder.reservations.release": {"risk_class": "MUTATE", "side_effects": True, "idempotent": False},
    "funder.commitments.prepare": {"risk_class": "PRIVILEGED", "side_effects": True, "idempotent": True},
    "funder.commitments.confirm": {"risk_class": "PRIVILEGED", "side_effects": True, "idempotent": True},
    "funder.exposure.get": {"risk_class": "SENSITIVE_READ", "side_effects": False, "idempotent": True},
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
    public_url = required("FUNDER_DEMO_PUBLIC_MCP_URL")
    tenant_id = required("FUNDER_DEMO_TENANT_ID")
    params = {"tenant_id": tenant_id}
    hostname = urlparse(public_url).hostname
    if not hostname:
        raise RuntimeError("FUNDER_DEMO_PUBLIC_MCP_URL must include a hostname.")
    async with httpx.AsyncClient(base_url=control_url, timeout=90) as client:
        response = await client.get("/internal/mcp/servers", params=params, headers=service_headers)
        response.raise_for_status()
        server = next((item for item in response.json() if item["label"] == "funder"), None)
        if server is not None and (server["endpoint"].rstrip("/") != public_url.rstrip("/") or server["transport"] != "STREAMABLE_HTTP"):
            raise RuntimeError("The tenant already has a funder label with another endpoint or transport.")
        if server is None:
            response = await client.post(
                "/internal/mcp/servers", params=params, headers=service_headers,
                json={
                    "label": "funder", "description": "Synthetic funding marketplace",
                    "transport": "STREAMABLE_HTTP", "endpoint": public_url,
                    "auth_type": "BEARER", "secret_ref": "env://FUNDER_MARKETPLACE_MCP_TOKEN",
                    "trust_tier": "UNREVIEWED", "allowed_egress_hosts": [hostname],
                    "timeout_seconds": 30, "max_retries": 1,
                },
            )
            response.raise_for_status()
            server = response.json()
        server_id = server["id"]
        response = await client.post(f"/internal/mcp/servers/{server_id}/discover", params=params, headers=service_headers)
        response.raise_for_status()
        response = await client.post(f"/internal/mcp/servers/{server_id}/review", params=params, headers=review_headers, json={"trust_tier": "REVIEWED_INTERNAL", "status": "ACTIVE"})
        response.raise_for_status()
        response = await client.get(f"/internal/mcp/servers/{server_id}/tools", params=params, headers=review_headers)
        response.raise_for_status()
        latest: dict[str, dict[str, Any]] = {}
        for tool in response.json():
            latest.setdefault(tool["canonical_name"], tool)
        if set(latest) != set(TOOL_POLICIES):
            raise RuntimeError(f"Funder discovery mismatch. Missing={sorted(set(TOOL_POLICIES) - set(latest))}; unexpected={sorted(set(latest) - set(TOOL_POLICIES))}")
        for name, policy in TOOL_POLICIES.items():
            response = await client.post(
                f"/internal/mcp/tools/{latest[name]['tool_version_id']}/review",
                params=params, headers=review_headers,
                json={
                    "canonical_name": name, **policy, "required_roles": [],
                    "required_purposes": [], "required_consents": [],
                    "allowed_agents": ["xyena-supervisor"], "approval_mode": "POLICY",
                    "parallel_allowed": False, "hosted_mcp_allowed": False,
                    "timeout_seconds": 30, "maximum_result_bytes": 196608,
                },
            )
            response.raise_for_status()
    print(f"Activated {len(TOOL_POLICIES)} reviewed Funder tools on MCP server {server_id}.")


def main() -> None:
    asyncio.run(register())


if __name__ == "__main__":
    main()
