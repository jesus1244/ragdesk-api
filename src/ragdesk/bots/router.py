from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Query, status

from ragdesk.auth.dependencies import CurrentUser, SessionDep
from ragdesk.bots import service
from ragdesk.bots.schemas import BotCreate, BotRead, BotUpdate
from ragdesk.core.schemas import ErrorResponse, Page

router = APIRouter(prefix="/bots", tags=["bots"])

NOT_FOUND: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "Bot not found"}
}


@router.get("", response_model=Page[BotRead])
async def list_bots(
    user: CurrentUser,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[BotRead]:
    bots, total = await service.list_bots(session, user.id, limit=limit, offset=offset)
    return Page(
        items=[BotRead.model_validate(b) for b in bots], total=total, limit=limit, offset=offset
    )


@router.post("", response_model=BotRead, status_code=status.HTTP_201_CREATED)
async def create_bot(data: BotCreate, user: CurrentUser, session: SessionDep) -> BotRead:
    bot = await service.create_bot(session, user.id, data)
    return BotRead.model_validate(bot)


@router.get("/{bot_id}", response_model=BotRead, responses=NOT_FOUND)
async def get_bot(bot_id: UUID, user: CurrentUser, session: SessionDep) -> BotRead:
    return BotRead.model_validate(await service.get_owned_bot(session, user.id, bot_id))


@router.patch("/{bot_id}", response_model=BotRead, responses=NOT_FOUND)
async def update_bot(
    bot_id: UUID, data: BotUpdate, user: CurrentUser, session: SessionDep
) -> BotRead:
    bot = await service.get_owned_bot(session, user.id, bot_id)
    return BotRead.model_validate(await service.update_bot(session, bot, data))


@router.delete("/{bot_id}", status_code=status.HTTP_204_NO_CONTENT, responses=NOT_FOUND)
async def delete_bot(bot_id: UUID, user: CurrentUser, session: SessionDep) -> None:
    bot = await service.get_owned_bot(session, user.id, bot_id)
    await service.delete_bot(session, bot)
