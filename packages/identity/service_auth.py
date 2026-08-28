import secrets

from fastapi import Header, HTTPException, status

from packages.config import get_settings


async def require_service_token(authorization: str | None = Header(default=None)) -> None:
    configured = get_settings().service_token
    if configured is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service authentication is not configured.",
        )
    scheme, _, supplied = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not secrets.compare_digest(
        supplied, configured.get_secret_value()
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid service token."
        )


async def require_mcp_admin_token(x_mcp_admin_token: str | None = Header(default=None)) -> None:
    configured = get_settings().mcp_admin_token
    if configured is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MCP review authentication is not configured.",
        )
    if not x_mcp_admin_token or not secrets.compare_digest(
        x_mcp_admin_token, configured.get_secret_value()
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid MCP admin token."
        )
