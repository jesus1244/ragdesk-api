"""Turn a stored source into searchable chunks."""

from collections.abc import Awaitable, Callable
from uuid import UUID

import structlog
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import undefer

from ragdesk.core.config import get_settings
from ragdesk.core.embeddings import Embedder
from ragdesk.ingestion.chunking import chunk_sections
from ragdesk.ingestion.errors import IngestionError
from ragdesk.ingestion.extract import extract_sections
from ragdesk.ingestion.fetch import FetchedPage, fetch_url
from ragdesk.sources.models import Chunk, Source, SourceKind, SourceStatus

log = structlog.get_logger("ingestion")

Fetcher = Callable[[str], Awaitable[FetchedPage]]


async def ingest_source(
    session: AsyncSession, source_id: UUID, *, embedder: Embedder, fetcher: Fetcher = fetch_url
) -> bool:
    """Extract, chunk and embed one source, replacing its previous chunks in one transaction.

    Safe to run more than once: a source that is already ready, or was deleted, is left alone.
    Returns True when the source ended up ready. `IngestionError` is recorded on the source (the
    owner sees the message); provider failures (`EmbeddingError`) propagate so the job can retry.
    """
    source = await session.get(Source, source_id, options=[undefer(Source.raw)])
    if source is None or source.status == SourceStatus.READY:
        return source is not None

    source.status = SourceStatus.PROCESSING
    source.error = None
    await session.commit()

    try:
        data, content_type = await _load(source, fetcher)
        sections = await extract_sections(data, content_type=content_type, name=source.name)
        drafts = chunk_sections(sections, target=get_settings().chunk_target_chars)
        if not drafts:
            raise IngestionError("No readable text was found in this source")
        vectors = await embedder.embed_documents([(d.title, d.content) for d in drafts])
    except IngestionError as exc:
        await mark_failed(session, source_id, str(exc))
        return False

    await session.execute(delete(Chunk).where(Chunk.source_id == source.id))
    session.add_all(
        Chunk(
            source_id=source.id,
            bot_id=source.bot_id,
            position=position,
            title=draft.title,
            content=draft.content,
            embedding=vector,
        )
        for position, (draft, vector) in enumerate(zip(drafts, vectors, strict=True))
    )
    source.status = SourceStatus.READY
    source.chunk_count = len(drafts)
    source.raw = None
    await session.commit()
    log.info("source.ingested", source_id=str(source.id), chunks=len(drafts))
    return True


async def _load(source: Source, fetcher: Fetcher) -> tuple[bytes, str]:
    if source.kind == SourceKind.URL:
        if not source.url:
            raise IngestionError("The source has no URL")
        page = await fetcher(source.url)
        return page.body, page.content_type
    if source.raw is None or source.content_type is None:
        raise IngestionError("The uploaded content is no longer available; upload it again")
    return source.raw, source.content_type


async def mark_failed(session: AsyncSession, source_id: UUID, message: str) -> None:
    source = await session.get(Source, source_id)
    if source is None:
        return
    source.status = SourceStatus.FAILED
    source.error = message[:500]
    await session.commit()
    log.warning("source.failed", source_id=str(source_id), reason=message)
