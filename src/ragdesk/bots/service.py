from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ragdesk.bots.models import Bot
from ragdesk.bots.schemas import BotCreate, BotUpdate
from ragdesk.core.database import utcnow
from ragdesk.core.exceptions import NotFoundError


async def get_owned_bot(session: AsyncSession, owner_id: UUID, bot_id: UUID) -> Bot:
    """Load a bot by id **and** owner: another owner's bot looks the same as a missing one."""
    bot = await session.scalar(
        select(Bot).where(Bot.id == bot_id, Bot.owner_id == owner_id, Bot.deleted_at.is_(None))
    )
    if bot is None:
        raise NotFoundError("Bot not found")
    return bot


async def list_bots(
    session: AsyncSession, owner_id: UUID, *, limit: int, offset: int
) -> tuple[list[Bot], int]:
    where = (Bot.owner_id == owner_id, Bot.deleted_at.is_(None))
    total = await session.scalar(select(func.count()).select_from(Bot).where(*where)) or 0
    rows = await session.scalars(
        select(Bot).where(*where).order_by(Bot.created_at.desc()).limit(limit).offset(offset)
    )
    return list(rows), total


async def create_bot(session: AsyncSession, owner_id: UUID, data: BotCreate) -> Bot:
    bot = Bot(owner_id=owner_id, **data.model_dump())
    session.add(bot)
    await session.commit()
    return bot


async def update_bot(session: AsyncSession, bot: Bot, data: BotUpdate) -> Bot:
    for field, value in data.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(bot, field, value)
    await session.commit()
    return bot


async def delete_bot(session: AsyncSession, bot: Bot) -> None:
    """Soft delete: the widget stops answering at once; data is purged later."""
    bot.deleted_at = utcnow()
    await session.commit()
