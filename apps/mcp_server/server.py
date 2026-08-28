from typing import Any

from mcp.server import MCPServer

from packages.tools.core_handlers import platform_describe, tool_risk_explain

mcp = MCPServer("xyena-core")


@mcp.tool(name="xyena.platform.describe")
async def describe_platform() -> dict[str, Any]:
    """Describe the safe, domain-neutral capabilities and execution boundary of Xyena."""
    return await platform_describe({})


@mcp.tool(name="xyena.tools.explain_risk")
async def explain_tool_risk(risk_class: str = "READ") -> dict[str, Any]:
    """Explain a Guardian tool risk class without accessing tenant or financial data."""
    return await tool_risk_explain({"risk_class": risk_class})


mcp_app = mcp.streamable_http_app(
    streamable_http_path="/", stateless_http=True, json_response=True
)
