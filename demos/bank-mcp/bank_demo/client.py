import asyncio
import hashlib
import hmac
import json
import os
from uuid import uuid4

import httpx2
from dotenv import load_dotenv
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from .seed import DEMO_ORGANIZATION_ID, DEMO_TENANT_ID, DEMO_USER_ID

load_dotenv()


def required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} must be configured.")
    return value


def signed_meta(secret: str, canonical_name: str) -> dict[str, object]:
    envelope = {
        "tenant_id": DEMO_TENANT_ID,
        "organization_id": DEMO_ORGANIZATION_ID,
        "user_id": DEMO_USER_ID,
        "session_id": str(uuid4()),
        "run_id": str(uuid4()),
        "call_id": str(uuid4()),
        "correlation_id": str(uuid4()),
        "agent_name": "xyena-supervisor",
        "canonical_name": canonical_name,
        "purpose": "synthetic bank MCP connection check",
        "request_hash": hashlib.sha256(canonical_name.encode()).hexdigest(),
    }
    canonical = json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode()
    signature = hmac.new(secret.encode(), canonical, hashlib.sha256).hexdigest()
    return {
        "ai.xyena/runtime": envelope,
        "ai.xyena/signature": signature,
        "ai.xyena/signature-algorithm": "hmac-sha256",
    }


async def check_connection() -> None:
    endpoint = os.getenv("BANK_DEMO_MCP_URL", "http://localhost:8090/mcp")
    token = required("BANK_DEMO_MCP_TOKEN")
    async with httpx2.AsyncClient(
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
        follow_redirects=True,
    ) as http_client:
        transport = streamable_http_client(endpoint, http_client=http_client)
        async with Client(transport) as client:
            discovered = await client.list_tools()
            names = [tool.name for tool in discovered.tools]
            result = await client.call_tool(
                "accounts.list",
                {},
                meta=signed_meta(token, "bank.accounts.list"),
            )
    print(json.dumps({"tools": names, "accounts_result": result.model_dump(mode="json")}, indent=2))


def main() -> None:
    asyncio.run(check_connection())


if __name__ == "__main__":
    main()
