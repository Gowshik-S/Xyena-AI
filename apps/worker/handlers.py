from typing import Any
from uuid import UUID

import httpx
from openai import AsyncOpenAI
from sqlalchemy import select

from packages.agents import AgentRuntime
from packages.config import get_settings
from packages.contracts.tools import ToolCallResume
from packages.persistence import get_database
from packages.persistence.models.mcp import MCPToolCall
from packages.persistence.models.memory import MemoryRecord

agent_runtime = AgentRuntime()


async def handle_agent_run(*, tenant_id: UUID, run_id: str, **_: Any) -> None:
    await agent_runtime.execute(tenant_id, UUID(run_id))


async def handle_mcp_resume(
    *, tenant_id: UUID, tool_call_id: str, correlation_id: str, **_: Any
) -> None:
    settings = get_settings()
    token = settings.service_token
    if token is None:
        raise RuntimeError("Service token is not configured.")
    body = ToolCallResume(
        tenant_id=tenant_id,
        call_id=UUID(tool_call_id),
        correlation_id=UUID(correlation_id),
    )
    async with httpx.AsyncClient(base_url=str(settings.mcp_base_url), timeout=60) as client:
        response = await client.post(
            "/internal/mcp/calls/resume",
            json=body.model_dump(mode="json"),
            headers={"Authorization": f"Bearer {token.get_secret_value()}"},
        )
    response.raise_for_status()
    tool_result = response.json()
    async with get_database().session(tenant_id=tenant_id, service_role="worker") as db:
        call = await db.scalar(
            select(MCPToolCall).where(
                MCPToolCall.id == body.call_id,
                MCPToolCall.tenant_id == tenant_id,
            )
        )
        if call is None:
            raise RuntimeError("Resumed MCP call is unavailable.")
        run_id = call.run_id
    await agent_runtime.resume_after_tool(tenant_id, run_id, tool_result)


async def handle_memory_embed(*, tenant_id: UUID, memory_id: str, **_: Any) -> None:
    settings = get_settings()
    api_key = settings.openai_api_key
    if api_key is None:
        return
    async with get_database().session(tenant_id=tenant_id, service_role="worker") as db:
        record = await db.scalar(
            select(MemoryRecord).where(
                MemoryRecord.id == UUID(memory_id),
                MemoryRecord.tenant_id == tenant_id,
                MemoryRecord.status == "ACTIVE",
            )
        )
        if record is None or record.embedding is not None:
            return
        content = record.content
    client = AsyncOpenAI(api_key=api_key.get_secret_value())
    response = await client.embeddings.create(
        model=settings.openai_embedding_model,
        input=content,
        dimensions=1536,
    )
    embedding = response.data[0].embedding
    async with get_database().session(tenant_id=tenant_id, service_role="worker") as db:
        record = await db.get(MemoryRecord, UUID(memory_id))
        if record is not None and record.status == "ACTIVE":
            record.embedding = embedding
