from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ragdesk.core.config import get_settings
from ragdesk.core.exceptions import ConflictError, NotFoundError
from ragdesk.core.queue import get_queue
from ragdesk.sources.models import Source, SourceKind, SourceStatus


def ingest_job_id(source_id: UUID) -> str:
    """Deterministic job id: enqueueing the same source twice is a no-op while it is queued."""
    return f"ingest:{source_id}"


async def get_source(session: AsyncSession, bot_id: UUID, source_id: UUID) -> Source:
    """Load a source by id **and** bot. The caller has already proven ownership of the bot."""
    source = await session.scalar(
        select(Source).where(Source.id == source_id, Source.bot_id == bot_id)
    )
    if source is None:
        raise NotFoundError("Source not found")
    return source


async def list_sources(
    session: AsyncSession, bot_id: UUID, *, limit: int, offset: int
) -> tuple[list[Source], int]:
    total = (
        await session.scalar(
            select(func.count()).select_from(Source).where(Source.bot_id == bot_id)
        )
        or 0
    )
    rows = await session.scalars(
        select(Source)
        .where(Source.bot_id == bot_id)
        .order_by(Source.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(rows), total


async def create_source(
    session: AsyncSession,
    bot_id: UUID,
    *,
    kind: SourceKind,
    name: str,
    url: str | None = None,
    content_type: str | None = None,
    raw: bytes | None = None,
) -> Source:
    """Store the source and queue its ingestion. The commit happens before the job is queued."""
    count = await session.scalar(
        select(func.count()).select_from(Source).where(Source.bot_id == bot_id)
    )
    if (count or 0) >= get_settings().max_sources_per_bot:
        raise ConflictError("This bot has reached its limit of sources")
    source = Source(
        bot_id=bot_id, kind=kind, name=name, url=url, content_type=content_type, raw=raw
    )
    session.add(source)
    await session.commit()
    await get_queue().enqueue("ingest_source", str(source.id), job_id=ingest_job_id(source.id))
    return source


async def retry_source(session: AsyncSession, source: Source) -> Source:
    if source.status != SourceStatus.FAILED:
        raise ConflictError("Only failed sources can be retried")
    source.status = SourceStatus.PENDING
    source.error = None
    await session.commit()
    await get_queue().enqueue("ingest_source", str(source.id), job_id=ingest_job_id(source.id))
    return source


async def delete_source(session: AsyncSession, source: Source) -> None:
    """Deleting the source removes its chunks (ON DELETE CASCADE)."""
    await session.delete(source)
    await session.commit()
