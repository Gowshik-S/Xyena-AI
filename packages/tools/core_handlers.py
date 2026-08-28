from typing import Any


async def platform_describe(arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        "platform": "Xyena + Guardian",
        "capabilities": [
            "tenant-isolated conversations",
            "multi-agent orchestration",
            "controlled MCP tools",
            "Guardian governance",
            "scoped context and memory",
        ],
        "execution_boundary": "No protected action executes without Guardian authorization.",
    }


async def tool_risk_explain(arguments: dict[str, Any]) -> dict[str, Any]:
    risk_class = str(arguments.get("risk_class", "READ")).upper()
    descriptions = {
        "READ": "Non-sensitive read under an explicit agent grant.",
        "SENSITIVE_READ": "Purpose, consent, scope, minimization, and audit are required.",
        "MUTATE": "State-changing call requiring idempotency and Guardian policy.",
        "PRIVILEGED": "High-impact call requiring exact Guardian authorization.",
    }
    return {"risk_class": risk_class, "description": descriptions.get(risk_class, "Unknown risk class")}


CORE_HANDLERS = {
    "xyena.platform.describe": platform_describe,
    "xyena.tools.explain_risk": tool_risk_explain,
}

