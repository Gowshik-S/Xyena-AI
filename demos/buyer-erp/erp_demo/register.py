import asyncio
import os
from typing import Any
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv


load_dotenv()

TOOL_NAMES = {
    "erp.counterparties.verify",
    "erp.purchase_orders.get",
    "erp.purchase_orders.find_by_invoice",
    "erp.receipts.get",
    "erp.invoice_matches.get",
    "erp.invoice_acceptance.get",
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
    public_url = required("ERP_DEMO_PUBLIC_MCP_URL")
    tenant_id = required("ERP_DEMO_TENANT_ID")
    params = {"tenant_id": tenant_id}
    hostname = urlparse(public_url).hostname
    if not hostname:
        raise RuntimeError("ERP_DEMO_PUBLIC_MCP_URL must include a hostname.")

    async with httpx.AsyncClient(base_url=control_url, timeout=90) as client:
        response = await client.get(
            "/internal/mcp/servers", params=params, headers=service_headers
        )
        response.raise_for_status()
        server = next((item for item in response.json() if item["label"] == "erp"), None)
        if server is not None and (
            server["endpoint"].rstrip("/") != public_url.rstrip("/")
            or server["transport"] != "STREAMABLE_HTTP"
        ):
            raise RuntimeError(
                "The tenant already has an ERP label with another endpoint or transport."
            )
        if server is None:
            response = await client.post(
                "/internal/mcp/servers",
                params=params,
                headers=service_headers,
                json={
                    "label": "erp",
                    "description": "Synthetic Buyer ERP operational evidence demo",
                    "transport": "STREAMABLE_HTTP",
                    "endpoint": public_url,
                    "auth_type": "BEARER",
                    "secret_ref": "env://BUYER_ERP_MCP_TOKEN",
                    "trust_tier": "UNREVIEWED",
                    "allowed_egress_hosts": [hostname],
                    "timeout_seconds": 30,
                    "max_retries": 1,
                },
            )
            response.raise_for_status()
            server = response.json()
        server_id = server["id"]
        response = await client.post(
            f"/internal/mcp/servers/{server_id}/discover",
            params=params,
            headers=service_headers,
        )
        response.raise_for_status()
        response = await client.post(
            f"/internal/mcp/servers/{server_id}/review",
            params=params,
            headers=review_headers,
            json={"trust_tier": "REVIEWED_INTERNAL", "status": "ACTIVE"},
        )
        response.raise_for_status()
        response = await client.get(
            f"/internal/mcp/servers/{server_id}/tools",
            params=params,
            headers=review_headers,
        )
        response.raise_for_status()
        latest: dict[str, dict[str, Any]] = {}
        for tool in response.json():
            latest.setdefault(tool["canonical_name"], tool)
        if set(latest) != TOOL_NAMES:
            raise RuntimeError(
                f"ERP discovery mismatch. Missing={sorted(TOOL_NAMES - set(latest))}; "
                f"unexpected={sorted(set(latest) - TOOL_NAMES)}"
            )
        for name in sorted(TOOL_NAMES):
            response = await client.post(
                f"/internal/mcp/tools/{latest[name]['tool_version_id']}/review",
                params=params,
                headers=review_headers,
                json={
                    "canonical_name": name,
                    "risk_class": "SENSITIVE_READ",
                    "required_roles": [],
                    "required_purposes": [],
                    "required_consents": [],
                    "allowed_agents": ["xyena-supervisor"],
                    "approval_mode": "POLICY",
                    "side_effects": False,
                    "idempotent": True,
                    "parallel_allowed": False,
                    "hosted_mcp_allowed": False,
                    "timeout_seconds": 30,
                    "maximum_result_bytes": 196608,
                },
            )
            response.raise_for_status()
    print(f"Activated {len(TOOL_NAMES)} reviewed ERP tools on MCP server {server_id}.")


def main() -> None:
    asyncio.run(register())


if __name__ == "__main__":
    main()
