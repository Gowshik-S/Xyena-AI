# Xyena MCP service

The importable Python package lives at `apps/mcp_server` because Python module names cannot
contain hyphens. Run it with `python -m apps.mcp_server.main`. It exposes the hosted MCP endpoint
at `/mcp` and service-authenticated registry/broker controls under `/internal/mcp`.
