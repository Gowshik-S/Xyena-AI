import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import BrowserSession, User


SESSION_COOKIE = "registry_demo_session"


class AuthenticationError(RuntimeError):
    pass


class AuthorizationError(RuntimeError):
    pass


@dataclass(frozen=True)
class BrowserScope:
    session: BrowserSession
    user: User

    @property
    def tenant_id(self) -> str:
        return self.user.tenant_id

    @property
    def roles(self) -> set[str]:
        return set(self.user.roles)


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    actual_salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=actual_salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt${actual_salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, salt_hex, expected_hex = encoded.split("$", 2)
        if algorithm != "scrypt":
            return False
        candidate = hash_password(password, salt=bytes.fromhex(salt_hex)).split("$", 2)[2]
        return hmac.compare_digest(candidate, expected_hex)
    except (ValueError, TypeError):
        return False


def hash_token(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


async def authenticate(db: AsyncSession, email: str, password: str) -> User:
    user = await db.scalar(select(User).where(User.email == email.lower(), User.status == "ACTIVE"))
    if user is None or not verify_password(password, user.password_hash):
        raise AuthenticationError("The email or password was not accepted.")
    return user


async def create_browser_session(db: AsyncSession, user: User) -> tuple[str, str]:
    raw_token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(24)
    db.add(
        BrowserSession(
            id=str(uuid4()),
            token_hash=hash_token(raw_token),
            csrf_hash=hash_token(csrf_token),
            user_id=user.id,
            tenant_id=user.tenant_id,
            expires_at=datetime.now(UTC) + timedelta(hours=8),
        )
    )
    user.last_login_at = datetime.now(UTC)
    return raw_token, csrf_token


async def resolve_browser_scope(db: AsyncSession, token: str | None) -> BrowserScope:
    if not token:
        raise AuthenticationError("Sign in to continue.")
    row = (
        await db.execute(
            select(BrowserSession, User)
            .join(User, User.id == BrowserSession.user_id)
            .where(BrowserSession.token_hash == hash_token(token))
        )
    ).first()
    if row is None:
        raise AuthenticationError("The session is invalid.")
    browser_session, user = row
    expires_at = browser_session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= datetime.now(UTC):
        raise AuthenticationError("The session has expired.")
    if user.status != "ACTIVE" or browser_session.tenant_id != user.tenant_id:
        raise AuthorizationError("The user or tenant scope is inactive.")
    browser_session.last_seen_at = datetime.now(UTC)
    return BrowserScope(browser_session, user)


def require_roles(scope: BrowserScope, *allowed: str) -> None:
    if not scope.roles.intersection(allowed):
        raise AuthorizationError("This account is not permitted to perform that action.")


def verify_csrf(scope: BrowserScope, supplied: str | None) -> None:
    if supplied is None or not hmac.compare_digest(hash_token(supplied), scope.session.csrf_hash):
        raise AuthorizationError("The form security token is missing or invalid.")


def rotate_csrf(scope: BrowserScope) -> str:
    token = secrets.token_urlsafe(24)
    scope.session.csrf_hash = hash_token(token)
    return token
