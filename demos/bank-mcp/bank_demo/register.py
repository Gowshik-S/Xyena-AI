import asyncio
import os
from typing import Any
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv

load_dotenv()


POLICIES: dict[str, dict[str, Any]] = {
    "bank.accounts.list": {"risk_class": "SENSITIVE_READ", "side_effects": False},
    "bank.accounts.get_balance": {
        "risk_class": "SENSITIVE_READ",
        "side_effects": False,
    },
    "bank.transactions.list": {
        "risk_class": "SENSITIVE_READ",
        "side_effects": False,
    },
    "bank.beneficiaries.verify": {
        "risk_class": "SENSITIVE_READ",
        "side_effects": False,
    },
    "bank.limits.get": {"risk_class": "SENSITIVE_READ", "side_effects": False},
    "bank.transfers.prepare": {"risk_class": "MUTATE", "side_effects": True},
    "bank.transfers.execute": {
        "risk_class": "PRIVILEGED",
        "side_effects": True,
        "approval_mode": "ALWAYS",
    },
    "bank.transfers.get_status": {
        "risk_class": "SENSITIVE_READ",
        "side_effects": False,
    },
}


def required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} must be configured.")
    return value


async def register() -> None:
    control_url = required("XYENA_MCP_CONTROL_URL").rstrip("/")
    service_token = required("XYENA_SERVICE_TOKEN")
    admin_token = required("XYENA_MCP_ADMIN_TOKEN")
    public_url = required("BANK_DEMO_PUBLIC_MCP_URL")
    tenant_id = required("BANK_DEMO_TENANT_ID")
    service_headers = {"Authorization": f"Bearer {service_token}"}
    review_headers = {"X-MCP-Admin-Token": admin_token}
    params = {"tenant_id": tenant_id}
    hostname = urlparse(public_url).hostname
    if not hostname:
        raise RuntimeError("BANK_DEMO_PUBLIC_MCP_URL must include a hostname.")

    async with httpx.AsyncClient(base_url=control_url, timeout=90) as client:
        response = await client.get("/internal/mcp/servers", params=params, headers=service_headers)
        response.raise_for_status()
        server = next((item for item in response.json() if item["label"] == "bank"), None)
        if server is not None and (
            server["endpoint"].rstrip("/") != public_url.rstrip("/")
            or server["transport"] != "STREAMABLE_HTTP"
        ):
            raise RuntimeError(
                "The tenant already has a bank MCP label with a different endpoint or transport."
            )
        if server is None:
            response = await client.post(
                "/internal/mcp/servers",
                params=params,
                headers=service_headers,
                json={
                    "label": "bank",
                    "description": (
                        "Isolated XYENA synthetic bank evidence and transfer-preparation demo"
                    ),
                    "transport": "STREAMABLE_HTTP",
                    "endpoint": public_url,
                    "auth_type": "BEARER",
                    "secret_ref": "env://BANK_DEMO_MCP_TOKEN",
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
        tools = response.json()
        latest: dict[str, dict[str, Any]] = {}
        for tool in tools:
            latest.setdefault(tool["canonical_name"], tool)

        missing = sorted(set(POLICIES) - set(latest))
        unexpected = sorted(set(latest) - set(POLICIES))
        if missing or unexpected:
            raise RuntimeError(
                f"Discovery review failed. Missing={missing}; unexpected={unexpected}."
            )

        for canonical_name, policy in POLICIES.items():
            tool = latest[canonical_name]
            response = await client.post(
                f"/internal/mcp/tools/{tool['tool_version_id']}/review",
                params=params,
                headers=review_headers,
                json={
                    "canonical_name": canonical_name,
                    "risk_class": policy["risk_class"],
                    "required_roles": [],
                    "required_purposes": [],
                    "required_consents": [],
                    "allowed_agents": ["xyena-supervisor"],
                    "approval_mode": policy.get("approval_mode", "POLICY"),
                    "side_effects": policy["side_effects"],
                    "idempotent": True,
                    "parallel_allowed": False,
                    "hosted_mcp_allowed": False,
                    "timeout_seconds": 30,
                    "maximum_result_bytes": 131072,
                },
            )
            response.raise_for_status()

    print(f"Activated {len(POLICIES)} reviewed bank tools on MCP server {server_id}.")


def main() -> None:
    asyncio.run(register())


if __name__ == "__main__":
    main()
