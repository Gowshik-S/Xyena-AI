import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from .secrets import SecretResolver


@dataclass(frozen=True)
class RemoteServerConfig:
    endpoint: str
    auth_type: str
    secret_ref: str | None
    timeout_seconds: float
    max_retries: int


class RemoteMCPClient:
    def __init__(self, secret_resolver: SecretResolver | None = None) -> None:
        self.secret_resolver = secret_resolver or SecretResolver()

    async def list_tools(self, config: RemoteServerConfig) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        async with self._client(config) as client:
            result = await client.list_tools()
            tools = []
            for tool in getattr(result, "tools", result):
                tools.append(
                    {
                        "name": getattr(tool, "name"),
                        "description": getattr(tool, "description", None),
                        "input_schema": getattr(tool, "inputSchema", None)
                        or getattr(tool, "input_schema", {}),
                        "output_schema": getattr(tool, "outputSchema", None)
                        or getattr(tool, "output_schema", {})
                        or {},
                    }
                )
            info = {
                "implementation_name": getattr(getattr(client, "server_info", None), "name", None),
                "implementation_version": getattr(getattr(client, "server_info", None), "version", None),
                "protocol_version": str(getattr(client, "protocol_version", "")) or None,
            }
            return tools, info

    async def call_tool(
        self, config: RemoteServerConfig, tool_name: str, arguments: dict[str, Any]
    ) -> Any:
        last_error: Exception | None = None
        for attempt in range(config.max_retries + 1):
            try:
                async with self._client(config) as client:
                    result = await asyncio.wait_for(
                        client.call_tool(tool_name, arguments),
                        timeout=config.timeout_seconds,
                    )
                    if getattr(result, "isError", False) or getattr(result, "is_error", False):
                        raise RuntimeError("Remote MCP server returned a tool error")
                    structured = getattr(result, "structuredContent", None) or getattr(
                        result, "structured_content", None
                    )
                    if structured is not None:
                        return structured
                    return _content_projection(getattr(result, "content", result))
            except Exception as exc:
                last_error = exc
                if attempt >= config.max_retries:
                    break
                await asyncio.sleep(min(2**attempt, 8))
        assert last_error is not None
        raise last_error

    @asynccontextmanager
    async def _client(self, config: RemoteServerConfig) -> AsyncIterator[Client]:
        token = self.secret_resolver.resolve(config.secret_ref)
        if token:
            timeout = httpx2.Timeout(config.timeout_seconds, read=max(config.timeout_seconds, 300))
            async with httpx2.AsyncClient(
                headers={"Authorization": f"Bearer {token}"},
                timeout=timeout,
                follow_redirects=True,
            ) as http_client:
                transport = streamable_http_client(config.endpoint, http_client=http_client)
                async with Client(transport) as client:
                    yield client
            return
        async with Client(config.endpoint) as client:
            yield client


def _content_projection(content: Any) -> Any:
    if isinstance(content, (str, int, float, bool, dict, list)) or content is None:
        return content
    if hasattr(content, "model_dump"):
        return content.model_dump(mode="json")
    if isinstance(content, tuple):
        return [_content_projection(item) for item in content]
    return str(content)
