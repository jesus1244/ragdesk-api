from typing import Any
from uuid import UUID

from arq import Retry

from ragdesk.core.database import SessionFactory
from ragdesk.core.embeddings import EmbeddingError, get_embedder
from ragdesk.ingestion.service import ingest_source, mark_failed

MAX_TRIES = 3


async def ingest_source_job(ctx: dict[str, Any], source_id: str) -> str:
    """ARQ job `ingest_source`. Provider errors are retried with backoff, then recorded."""
    job_try: int = ctx.get("job_try", 1)
    async with SessionFactory() as session:
        try:
            ready = await ingest_source(session, UUID(source_id), embedder=get_embedder())
        except EmbeddingError as exc:
            if job_try < MAX_TRIES:
                raise Retry(defer=job_try * 20) from exc
            await mark_failed(
                session, UUID(source_id), "The embedding service is unavailable. Try again later."
            )
            return "failed"
    return "ready" if ready else "failed"
