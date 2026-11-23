from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Query

from ragdesk.auth.dependencies import CurrentUser, SessionDep
from ragdesk.bots.service import get_owned_bot
from ragdesk.chat.schemas import ConversationRead, MessageRead, UnansweredRead
from ragdesk.core.schemas import ErrorResponse, Page
from ragdesk.insights import service
from ragdesk.insights.schemas import BotStats

router = APIRouter(prefix="/bots/{bot_id}", tags=["insights"])

NOT_FOUND: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "Bot or conversation not found"}
}
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]


@router.get("/stats", response_model=BotStats, responses=NOT_FOUND)
async def stats(bot_id: UUID, user: CurrentUser, session: SessionDep) -> BotStats:
    await get_owned_bot(session, user.id, bot_id)
    return await service.bot_stats(session, bot_id)


@router.get("/conversations", response_model=Page[ConversationRead], responses=NOT_FOUND)
async def list_conversations(
    bot_id: UUID, user: CurrentUser, session: SessionDep, limit: Limit = 20, offset: Offset = 0
) -> Page[ConversationRead]:
    await get_owned_bot(session, user.id, bot_id)
    items, total = await service.list_conversations(session, bot_id, limit=limit, offset=offset)
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=list[MessageRead],
    responses=NOT_FOUND,
)
async def conversation_messages(
    bot_id: UUID, conversation_id: UUID, user: CurrentUser, session: SessionDep
) -> list[MessageRead]:
    await get_owned_bot(session, user.id, bot_id)
    messages = await service.get_conversation_messages(session, bot_id, conversation_id)
    return [MessageRead.model_validate(m) for m in messages]


@router.get("/unanswered", response_model=Page[UnansweredRead], responses=NOT_FOUND)
async def unanswered(
    bot_id: UUID, user: CurrentUser, session: SessionDep, limit: Limit = 20, offset: Offset = 0
) -> Page[UnansweredRead]:
    await get_owned_bot(session, user.id, bot_id)
    items, total = await service.list_unanswered(session, bot_id, limit=limit, offset=offset)
    return Page(items=items, total=total, limit=limit, offset=offset)
