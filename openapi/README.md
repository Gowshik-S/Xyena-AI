# OpenAPI artifacts

`scripts/export_openapi.py` exports service descriptions to `openapi/generated/`. Reviewed release snapshots and bundled YAML descriptions belong here once the implementation enters its release pipeline.

The MCP `/mcp` protocol endpoint is intentionally not represented as an arbitrary REST operation. MCP tool schemas are registered and versioned separately.

