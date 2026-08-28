import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import BrowserSession, Enterprise, EnterpriseMembership, User


SESSION_COOKIE = "gst_demo_session"


class AuthenticationError(RuntimeError):
    pass


class AuthorizationError(RuntimeError):
    pass


@dataclass(frozen=True)
class BrowserScope:
    session: BrowserSession
    user: User
    enterprise: Enterprise
    membership: EnterpriseMembership

    @property
    def roles(self) -> set[str]:
        return set(self.membership.roles)


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    actual_salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode(), salt=actual_salt, n=2**14, r=8, p=1, dklen=32
    )
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


async def create_browser_session(
    db: AsyncSession, user: User, enterprise_id: str | None = None
) -> tuple[BrowserSession, str, str]:
    memberships = (
        await db.scalars(
            select(EnterpriseMembership)
            .where(
                EnterpriseMembership.user_id == user.id,
                EnterpriseMembership.status == "ACTIVE",
            )
            .order_by(EnterpriseMembership.enterprise_id)
        )
    ).all()
    if not memberships:
        raise AuthorizationError("The test user has no active enterprise membership.")
    membership = next(
        (value for value in memberships if value.enterprise_id == enterprise_id), memberships[0]
    )
    token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(24)
    value = BrowserSession(
        id=str(uuid4()),
        token_hash=hash_token(token),
        csrf_hash=hash_token(csrf_token),
        user_id=user.id,
        enterprise_id=membership.enterprise_id,
        expires_at=datetime.now(UTC) + timedelta(hours=8),
    )
    user.last_login_at = datetime.now(UTC)
    db.add(value)
    return value, token, csrf_token


async def resolve_browser_scope(db: AsyncSession, token: str | None) -> BrowserScope:
    if not token:
        raise AuthenticationError("Sign in to continue.")
    row = (
        await db.execute(
            select(BrowserSession, User, Enterprise, EnterpriseMembership)
            .join(User, User.id == BrowserSession.user_id)
            .join(Enterprise, Enterprise.id == BrowserSession.enterprise_id)
            .join(
                EnterpriseMembership,
                (EnterpriseMembership.user_id == BrowserSession.user_id)
                & (EnterpriseMembership.enterprise_id == BrowserSession.enterprise_id),
            )
            .where(BrowserSession.token_hash == hash_token(token))
        )
    ).first()
    if row is None:
        raise AuthenticationError("The session is invalid.")
    browser_session, user, enterprise, membership = row
    expires_at = browser_session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= datetime.now(UTC):
        raise AuthenticationError("The session has expired.")
    if any(value.status != "ACTIVE" for value in (user, enterprise, membership)):
        raise AuthorizationError("The user or enterprise membership is inactive.")
    browser_session.last_seen_at = datetime.now(UTC)
    return BrowserScope(browser_session, user, enterprise, membership)


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
