import hashlib
from datetime import UTC, datetime
from uuid import UUID, uuid5, NAMESPACE_URL

import jwt
from jwt import PyJWKClient

from packages.config import Settings
from packages.contracts.identity import AuthenticatedPrincipal


class AuthenticationError(Exception):
    pass


class TokenAuthenticator:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._jwks_client = PyJWKClient(settings.jwks_url, cache_keys=True, lifespan=300)

    def authenticate(self, token: str) -> AuthenticatedPrincipal:
        try:
            signing_key = self._jwks_client.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256", "ES256"],
                audience=self.settings.oidc_audience,
                issuer=self.settings.oidc_issuer,
                options={"require": ["exp", "iat", "sub"]},
            )
        except Exception as exc:
            raise AuthenticationError("Invalid or expired access token") from exc

        try:
            return AuthenticatedPrincipal(
                subject=claims["sub"],
                tenant_id=UUID(claims["tenant_id"]),
                organization_id=UUID(claims["organization_id"]),
                user_id=UUID(claims["user_id"]),
                roles=tuple(claims.get("roles", [])),
                scopes=tuple(str(claims.get("scope", "")).split()),
                expires_at=datetime.fromtimestamp(claims["exp"], tz=UTC),
            )
        except (KeyError, ValueError, TypeError) as exc:
            raise AuthenticationError("Required identity scope is missing") from exc

    def development_principal(
        self,
        *,
        tenant: str,
        organization: str,
        user: str,
        roles: tuple[str, ...] = ("XYENA_USER",),
    ) -> AuthenticatedPrincipal:
        if not self.settings.dev_auth_bypass:
            raise AuthenticationError("Development authentication bypass is disabled")
        return AuthenticatedPrincipal(
            subject=f"dev:{hashlib.sha256(user.encode()).hexdigest()[:16]}",
            tenant_id=_parse_or_derive_uuid("tenant", tenant),
            organization_id=_parse_or_derive_uuid("organization", organization),
            user_id=_parse_or_derive_uuid("user", user),
            roles=roles,
            scopes=("xyena:use",),
        )


def _parse_or_derive_uuid(namespace: str, value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError:
        return uuid5(NAMESPACE_URL, f"xyena:{namespace}:{value}")

