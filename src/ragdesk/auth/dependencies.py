from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from ragdesk.auth.models import User
from ragdesk.core.database import get_session
from ragdesk.core.exceptions import UnauthorizedError
from ragdesk.core.security import decode_token

SessionDep = Annotated[AsyncSession, Depends(get_session)]

_bearer = HTTPBearer(auto_error=False, description="JWT access token")


async def user_from_access_token(session: AsyncSession, token: str) -> User:
    try:
        payload = decode_token(token, "access")
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError("Access token expired") from exc
    except jwt.PyJWTError as exc:
        raise UnauthorizedError("Invalid access token") from exc
    user = await session.get(User, UUID(payload["sub"]))
    if user is None or not user.is_active:
        raise UnauthorizedError("User not found or inactive")
    return user


async def get_current_user(
    session: SessionDep,
    bearer: Annotated[HTTPAuthorizationCredentials | None, Security(_bearer)],
) -> User:
    """Authenticate with `Authorization: Bearer <jwt>`."""
    if bearer is None:
        raise UnauthorizedError()
    return await user_from_access_token(session, bearer.credentials)


CurrentUser = Annotated[User, Depends(get_current_user)]
