from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ragdesk.chat.models import Conversation, Message, MessageRole
from ragdesk.chat.schemas import ConversationRead, UnansweredRead
from ragdesk.core.exceptions import NotFoundError
from ragdesk.insights.schemas import BotStats


async def list_conversations(
    session: AsyncSession, bot_id: UUID, *, limit: int, offset: int
) -> tuple[list[ConversationRead], int]:
    total = await session.scalar(
        select(func.count()).select_from(Conversation).where(Conversation.bot_id == bot_id)
    )
    last_activity = func.max(Message.created_at)
    rows = await session.execute(
        select(
            Conversation,
            func.count(Message.id),
            func.min(Message.content).filter(Message.role == MessageRole.USER),
        )
        .outerjoin(Message, Message.conversation_id == Conversation.id)
        .where(Conversation.bot_id == bot_id)
        .group_by(Conversation.id)
        .order_by(last_activity.desc().nulls_last(), Conversation.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    items = [
        ConversationRead(
            id=c.id,
            visitor_id=c.visitor_id,
            created_at=c.created_at,
            message_count=count,
            last_question=question,
        )
        for c, count, question in rows
    ]
    return items, total or 0


async def get_conversation_messages(
    session: AsyncSession, bot_id: UUID, conversation_id: UUID
) -> list[Message]:
    conversation = await session.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id, Conversation.bot_id == bot_id
        )
    )
    if conversation is None:
        raise NotFoundError("Conversation not found")
    rows = await session.scalars(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at, Message.role.desc())
    )
    return list(rows)


async def list_unanswered(
    session: AsyncSession, bot_id: UUID, *, limit: int, offset: int
) -> tuple[list[UnansweredRead], int]:
    condition = (Message.bot_id == bot_id) & (Message.answered.is_(False))
    total = await session.scalar(select(func.count()).select_from(Message).where(condition))
    rows = await session.scalars(
        select(Message)
        .where(condition)
        .order_by(Message.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    items = [
        UnansweredRead(
            message_id=m.id,
            conversation_id=m.conversation_id,
            question=m.question or "",
            created_at=m.created_at,
        )
        for m in rows
    ]
    return items, total or 0


async def bot_stats(session: AsyncSession, bot_id: UUID) -> BotStats:
    conversations = await session.scalar(
        select(func.count()).select_from(Conversation).where(Conversation.bot_id == bot_id)
    )
    row = (
        await session.execute(
            select(
                func.count(),
                func.count().filter(Message.answered.is_(True)),
                func.count().filter(Message.answered.is_(False)),
            ).where(Message.bot_id == bot_id, Message.role == MessageRole.ASSISTANT)
        )
    ).one()
    questions, answered, unanswered = row
    return BotStats(
        conversations=conversations or 0,
        questions=questions,
        answered=answered,
        unanswered=unanswered,
        answer_rate=round(answered / questions, 3) if questions else 0.0,
    )
