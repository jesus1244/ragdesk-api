from httpx import AsyncClient
from sqlalchemy import func, select

from ragdesk.core.database import SessionFactory
from ragdesk.core.embeddings import FakeEmbedder
from ragdesk.demo.content import DEMO_DOCUMENTS
from ragdesk.demo.seed import seed_demo
from ragdesk.sources.models import Chunk, Source, SourceStatus
from tests.test_chat import _ask, parse_sse


async def _seed() -> tuple[str, bool]:
    async with SessionFactory() as session:
        bot, created = await seed_demo(
            session, embedder=FakeEmbedder(), email="demo@example.com", password="Demo1234pass"
        )
        return bot.public_key, created


async def test_seed_creates_a_demo_bot_with_ready_sources() -> None:
    _, created = await _seed()
    assert created is True
    async with SessionFactory() as session:
        statuses = set(await session.scalars(select(Source.status)))
        chunks = await session.scalar(select(func.count()).select_from(Chunk))
    assert statuses == {SourceStatus.READY}
    assert (chunks or 0) >= len(DEMO_DOCUMENTS)


async def test_seed_is_idempotent() -> None:
    first_key, _ = await _seed()
    second_key, created = await _seed()
    assert second_key == first_key
    assert created is False
    async with SessionFactory() as session:
        sources = await session.scalar(select(func.count()).select_from(Source))
    assert sources == len(DEMO_DOCUMENTS)


async def test_demo_assistant_answers_from_its_documents(client: AsyncClient) -> None:
    key, _ = await _seed()
    events = parse_sse(await _ask(client, key, "refunds go back to the original payment method"))
    citations = dict(events)["citations"]
    assert citations[0]["source_name"] == "returns-and-refunds.md"
    assert dict(events)["done"] == {"answered": True}
