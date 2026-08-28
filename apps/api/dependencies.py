from collections.abc import AsyncIterator
from functools import lru_cache
from uuid import UUID, uuid4

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from packages.config import Settings, get_settings
from packages.contracts.identity import AuthenticatedPrincipal
from packages.identity import AuthenticationError, TokenAuthenticator
from packages.observability import bind_context
from packages.persistence import get_database

bearer = HTTPBearer(auto_error=False)


@lru_cache(maxsize=1)
def get_authenticator() -> TokenAuthenticator:
    return TokenAuthenticator(get_settings())


async def get_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    authenticator: TokenAuthenticator = Depends(get_authenticator),
    settings: Settings = Depends(get_settings),
    x_dev_tenant: str | None = Header(default=None),
    x_dev_organization: str | None = Header(default=None),
    x_dev_user: str | None = Header(default=None),
) -> AuthenticatedPrincipal:
    try:
        if credentials is not None:
            return authenticator.authenticate(credentials.credentials)
        if settings.dev_auth_bypass and x_dev_tenant and x_dev_organization and x_dev_user:
            return authenticator.development_principal(
                tenant=x_dev_tenant,
                organization=x_dev_organization,
                user=x_dev_user,
            )
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")


async def get_correlation_id(request: Request) -> UUID:
    value = getattr(request.state, "correlation_id", None)
    return value if isinstance(value, UUID) else uuid4()


async def get_scoped_session(
    principal: AuthenticatedPrincipal = Depends(get_principal),
) -> AsyncIterator[AsyncSession]:
    bind_context(
        tenant_id=str(principal.tenant_id),
        organization_id=str(principal.organization_id),
        user_id=str(principal.user_id),
    )
    database = get_database()
    async with database.session(
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        service_role="api",
    ) as session:
        yield session

