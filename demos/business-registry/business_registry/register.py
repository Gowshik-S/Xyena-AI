import asyncio
import os
from typing import Any
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv


load_dotenv()

POLICIES: dict[str, dict[str, Any]] = {
    "registry.businesses.get": {"risk_class": "SENSITIVE_READ"},
    "registry.businesses.verify": {"risk_class": "SENSITIVE_READ"},
    "registry.businesses.search": {"risk_class": "SENSITIVE_READ"},
    "registry.ownership.get": {"risk_class": "SENSITIVE_READ"},
    "registry.relationships.get": {"risk_class": "SENSITIVE_READ"},
    "registry.authorized_persons.get": {"risk_class": "SENSITIVE_READ"},
}


def required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} must be configured.")
    return value


async def register() -> None:
    control_url = required("XYENA_MCP_CONTROL_URL").rstrip("/")
    public_url = required("REGISTRY_DEMO_PUBLIC_MCP_URL")
    tenant_ids = [
        value.strip() for value in required("REGISTRY_DEMO_TENANT_IDS").split(",") if value.strip()
    ]
    hostname = urlparse(public_url).hostname
    if not hostname:
        raise RuntimeError("REGISTRY_DEMO_PUBLIC_MCP_URL must include a hostname.")
    service_headers = {"Authorization": f"Bearer {required('XYENA_SERVICE_TOKEN')}"}
    review_headers = {"X-MCP-Admin-Token": required("XYENA_MCP_ADMIN_TOKEN")}
    async with httpx.AsyncClient(base_url=control_url, timeout=90) as client:
        for tenant_id in tenant_ids:
            await _register_tenant(
                client, tenant_id, public_url, hostname, service_headers, review_headers
            )
    print(f"Activated {len(POLICIES)} reviewed Registry tools for {len(tenant_ids)} tenants.")


async def _register_tenant(
    client: httpx.AsyncClient,
    tenant_id: str,
    public_url: str,
    hostname: str,
    service_headers: dict[str, str],
    review_headers: dict[str, str],
) -> None:
    params = {"tenant_id": tenant_id}
    response = await client.get("/internal/mcp/servers", params=params, headers=service_headers)
    response.raise_for_status()
    server = next((item for item in response.json() if item["label"] == "registry"), None)
    if server is not None and (
        server["endpoint"].rstrip("/") != public_url.rstrip("/")
        or server["transport"] != "STREAMABLE_HTTP"
    ):
        raise RuntimeError(f"Tenant {tenant_id} already has a different Registry MCP server.")
    if server is None:
        response = await client.post(
            "/internal/mcp/servers", params=params, headers=service_headers,
            json={
                "label": "registry", "description": "XYENA synthetic business identity registry",
                "transport": "STREAMABLE_HTTP", "endpoint": public_url,
                "auth_type": "BEARER", "secret_ref": "env://REGISTRY_DEMO_MCP_TOKEN",
                "trust_tier": "UNREVIEWED", "allowed_egress_hosts": [hostname],
                "timeout_seconds": 30, "max_retries": 1,
            },
        )
        response.raise_for_status()
        server = response.json()
    server_id = server["id"]
    response = await client.post(
        f"/internal/mcp/servers/{server_id}/discover", params=params, headers=service_headers
    )
    response.raise_for_status()
    response = await client.post(
        f"/internal/mcp/servers/{server_id}/review", params=params, headers=review_headers,
        json={"trust_tier": "REVIEWED_INTERNAL", "status": "ACTIVE"},
    )
    response.raise_for_status()
    response = await client.get(
        f"/internal/mcp/servers/{server_id}/tools", params=params, headers=review_headers
    )
    response.raise_for_status()
    latest: dict[str, dict[str, Any]] = {}
    for tool in response.json():
        latest.setdefault(tool["canonical_name"], tool)
    if set(latest) != set(POLICIES):
        raise RuntimeError(
            f"Registry discovery mismatch for tenant {tenant_id}: "
            f"missing={sorted(set(POLICIES) - set(latest))}, "
            f"unexpected={sorted(set(latest) - set(POLICIES))}"
        )
    for canonical_name, policy in POLICIES.items():
        response = await client.post(
            f"/internal/mcp/tools/{latest[canonical_name]['tool_version_id']}/review",
            params=params, headers=review_headers,
            json={
                "canonical_name": canonical_name, "risk_class": policy["risk_class"],
                "required_roles": [], "required_purposes": [], "required_consents": [],
                "allowed_agents": ["xyena-supervisor"],
                "approval_mode": "POLICY", "side_effects": False, "idempotent": True,
                "parallel_allowed": True, "hosted_mcp_allowed": False,
                "timeout_seconds": 30, "maximum_result_bytes": 262144,
            },
        )
        response.raise_for_status()


def main() -> None:
    asyncio.run(register())


if __name__ == "__main__":
    main()
