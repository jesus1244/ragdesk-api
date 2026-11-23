from datetime import timedelta
from uuid import UUID, uuid4

import jwt
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ragdesk.auth.models import RefreshToken, User
from ragdesk.auth.schemas import RegisterRequest, TokenPair
from ragdesk.core.config import get_settings
from ragdesk.core.database import utcnow
from ragdesk.core.exceptions import ConflictError, UnauthorizedError
from ragdesk.core.security import (
    create_token,
    decode_token,
    hash_password,
    verify_password,
)

# Pre-computed hash used to keep login timing constant when the email does not exist.
_DUMMY_HASH = hash_password("dummy-password-for-timing")


async def register_user(session: AsyncSession, data: RegisterRequest) -> User:
    exists = await session.scalar(select(User.id).where(User.email == data.email))
    if exists:
        raise ConflictError("Email is already registered")
    user = User(
        email=data.email, full_name=data.full_name, password_hash=hash_password(data.password)
    )
    session.add(user)
    await session.commit()
    return user


async def authenticate(session: AsyncSession, email: str, password: str) -> User:
    user = await session.scalar(select(User).where(User.email == email.lower()))
    if user is None:
        verify_password(password, _DUMMY_HASH)
        raise UnauthorizedError("Invalid email or password")
    if not verify_password(password, user.password_hash) or not user.is_active:
        raise UnauthorizedError("Invalid email or password")
    return user


async def issue_tokens(
    session: AsyncSession, user_id: UUID, family_id: UUID | None = None
) -> TokenPair:
    settings = get_settings()
    jti = uuid4()
    session.add(
        RefreshToken(
            id=jti,
            user_id=user_id,
            family_id=family_id or uuid4(),
            expires_at=utcnow() + timedelta(days=settings.refresh_token_ttl_days),
        )
    )
    await session.commit()
    return TokenPair(
        access_token=create_token(user_id, "access"),
        refresh_token=create_token(user_id, "refresh", jti=jti),
        expires_in=settings.access_token_ttl_minutes * 60,
    )


async def rotate_refresh_token(session: AsyncSession, refresh_token: str) -> TokenPair:
    """Exchange a refresh token for a new pair (rotation).

    If an already-used token is presented again, the whole token family is revoked:
    that is the standard signal that a refresh token was stolen.
    """
    try:
        payload = decode_token(refresh_token, "refresh")
    except jwt.PyJWTError as exc:
        raise UnauthorizedError("Invalid refresh token") from exc

    stored = await session.get(RefreshToken, UUID(payload["jti"]))
    if stored is None or stored.expires_at < utcnow():
        raise UnauthorizedError("Invalid refresh token")
    if stored.revoked_at is not None:
        await _revoke_family(session, stored.family_id)
        await session.commit()
        raise UnauthorizedError("Refresh token reuse detected; please log in again")

    stored.revoked_at = utcnow()
    return await issue_tokens(session, stored.user_id, family_id=stored.family_id)


async def revoke_refresh_token(session: AsyncSession, refresh_token: str) -> None:
    try:
        payload = decode_token(refresh_token, "refresh")
    except jwt.PyJWTError:
        return  # logout is idempotent
    stored = await session.get(RefreshToken, UUID(payload["jti"]))
    if stored is not None:
        await _revoke_family(session, stored.family_id)
        await session.commit()


async def _revoke_family(session: AsyncSession, family_id: UUID) -> None:
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
