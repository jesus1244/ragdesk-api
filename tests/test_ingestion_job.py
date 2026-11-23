from collections.abc import Sequence
from uuid import UUID

import pytest
from arq import Retry
from httpx import AsyncClient
from sqlalchemy import select

from ragdesk.core import embeddings
from ragdesk.core.database import SessionFactory
from ragdesk.core.embeddings import EmbeddingError
from ragdesk.ingestion.tasks import MAX_TRIES, ingest_source_job
from ragdesk.sources.models import Source, SourceStatus


class _DownEmbedder:
    async def embed_documents(self, items: Sequence[tuple[str, str]]) -> list[list[float]]:
        raise EmbeddingError("provider down")

    async def embed_query(self, text: str) -> list[float]:
        raise EmbeddingError("provider down")


async def _pending_source(client: AsyncClient, headers: dict[str, str]) -> tuple[str, str]:
    """Create a source while the embedder works, then reset it to pending."""
    bot_id = (await client.post("/bots", json={"name": "Docs bot"}, headers=headers)).json()["id"]
    created = await client.post(
        f"/bots/{bot_id}/sources/text",
        json={"name": "FAQ", "text": "We open at 9am."},
        headers=headers,
    )
    source_id = created.json()["id"]
    async with SessionFactory() as session:
        source = await session.get(Source, UUID(source_id))
        assert source is not None
        source.status = SourceStatus.PENDING
        source.raw = b"We open at 9am."
        await session.commit()
    return bot_id, source_id


async def test_provider_failure_is_retried_before_giving_up(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    _, source_id = await _pending_source(client, auth_headers)
    embeddings.set_embedder(_DownEmbedder())

    with pytest.raises(Retry):
        await ingest_source_job({"job_try": 1}, source_id)

    result = await ingest_source_job({"job_try": MAX_TRIES}, source_id)
    assert result == "failed"
    async with SessionFactory() as session:
        source = (await session.scalars(select(Source).where(Source.id == UUID(source_id)))).one()
        assert source.status == SourceStatus.FAILED
        assert source.error == "The embedding service is unavailable. Try again later."
        assert "provider down" not in source.error


async def test_job_for_a_deleted_source_is_a_no_op() -> None:
    assert await ingest_source_job({"job_try": 1}, str(UUID(int=1))) == "failed"
