import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import jwt

from packages.config import get_settings


class AuthorizationSigningError(RuntimeError):
    pass


class AuthorizationSigner:
    issuer = "xyena-guardian"
    audience = "xyena-mcp"

    def issue(
        self,
        *,
        authorization_id: UUID,
        tenant_id: UUID,
        call_id: UUID,
        decision_id: UUID,
        request_hash: str,
        constraints: dict[str, Any],
        lifetime_seconds: int = 120,
    ) -> tuple[str, UUID, datetime]:
        private_key = get_settings().guardian_signing_key
        if private_key is None:
            raise AuthorizationSigningError("Guardian signing key is not configured.")
        now = datetime.now(UTC)
        expires_at = now + timedelta(seconds=lifetime_seconds)
        token_id = uuid4()
        claims = {
            "iss": self.issuer,
            "aud": self.audience,
            "sub": str(authorization_id),
            "jti": str(token_id),
            "tenant_id": str(tenant_id),
            "call_id": str(call_id),
            "decision_id": str(decision_id),
            "request_hash": request_hash,
            "constraints": constraints,
            "iat": now,
            "nbf": now,
            "exp": expires_at,
        }
        key = private_key.get_secret_value().replace("\\n", "\n")
        return jwt.encode(claims, key, algorithm="EdDSA"), token_id, expires_at

    def verify(self, token: str) -> dict[str, Any]:
        verify_key = get_settings().guardian_verify_key
        if verify_key is None:
            raise AuthorizationSigningError("Guardian verification key is not configured.")
        key = verify_key.get_secret_value().replace("\\n", "\n")
        try:
            return jwt.decode(
                token,
                key,
                algorithms=["EdDSA"],
                audience=self.audience,
                issuer=self.issuer,
                options={"require": ["exp", "iat", "nbf", "jti", "sub"]},
            )
        except jwt.PyJWTError as exc:
            raise AuthorizationSigningError("Guardian authorization is invalid.") from exc


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
