from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import Header, HTTPException, status

from .constants import DEMO_TENANT_ID
from .settings import get_settings


@dataclass(frozen=True)
class ActorScope:
    tenant_id: str
    actor_id: str
    role: str


def _token_map() -> dict[str, ActorScope]:
    settings = get_settings()
    entries = (
        (settings.viewer_token, "demo_viewer", "DEMO_VIEWER"),
        (settings.seller_token, "seller_operator", "SELLER_OPERATOR"),
        (settings.carrier_token, "carrier_operator", "CARRIER_OPERATOR"),
        (settings.buyer_token, "buyer_receiver", "BUYER_RECEIVER"),
        (settings.reviewer_token, "delivery_reviewer", "DELIVERY_REVIEWER"),
        (settings.admin_token, "delivery_admin", "DEMO_ADMIN"),
    )
    return {
        secret.get_secret_value(): ActorScope(DEMO_TENANT_ID, actor_id, role)
        for secret, actor_id, role in entries
    }


def authenticate_token(token: str | None) -> ActorScope:
    scope = _token_map().get(token or "")
    if scope is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A valid delivery demo role token is required.",
        )
    return scope


async def resolve_actor(
    x_demo_token: Annotated[str | None, Header(alias="X-Demo-Token")] = None,
) -> ActorScope:
    return authenticate_token(x_demo_token)


def require_roles(*allowed_roles: str) -> Callable[..., ActorScope]:
    async def dependency(
        x_demo_token: Annotated[str | None, Header(alias="X-Demo-Token")] = None,
    ) -> ActorScope:
        scope = authenticate_token(x_demo_token)
        if scope.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This operation requires one of: {', '.join(allowed_roles)}.",
            )
        return scope

    return dependency
