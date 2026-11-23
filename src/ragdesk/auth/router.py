from fastapi import APIRouter, Depends, status

from ragdesk.auth import service
from ragdesk.auth.dependencies import CurrentUser, SessionDep
from ragdesk.auth.schemas import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
    UserRead,
)
from ragdesk.core.config import get_settings
from ragdesk.core.rate_limit import rate_limit
from ragdesk.core.schemas import ErrorResponse

_limit = get_settings().rate_limit_auth_per_minute

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("register", _limit))],
    responses={409: {"model": ErrorResponse, "description": "Email already registered"}},
)
async def register(data: RegisterRequest, session: SessionDep) -> UserRead:
    user = await service.register_user(session, data)
    return UserRead.model_validate(user)


@router.post(
    "/login",
    response_model=TokenPair,
    dependencies=[Depends(rate_limit("login", _limit))],
    responses={401: {"model": ErrorResponse}},
)
async def login(data: LoginRequest, session: SessionDep) -> TokenPair:
    user = await service.authenticate(session, data.email, data.password)
    return await service.issue_tokens(session, user.id)


@router.post("/refresh", response_model=TokenPair, responses={401: {"model": ErrorResponse}})
async def refresh(data: RefreshRequest, session: SessionDep) -> TokenPair:
    return await service.rotate_refresh_token(session, data.refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(data: RefreshRequest, session: SessionDep) -> None:
    await service.revoke_refresh_token(session, data.refresh_token)


@router.get("/me", response_model=UserRead)
async def me(user: CurrentUser) -> UserRead:
    return UserRead.model_validate(user)
