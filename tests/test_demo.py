from httpx import AsyncClient
from sqlalchemy import func, select

from ragdesk.core.database import SessionFactory
from ragdesk.core.embeddings import FakeEmbedder
from ragdesk.demo.content import DEMO_ASSISTANTS
from ragdesk.demo.seed import seed_demo
from ragdesk.sources.models import Chunk, Source, SourceStatus
from tests.test_chat import _ask, parse_sse


async def _seed() -> tuple[dict[str, str], bool]:
    """Returns the widget key of each demo assistant by language."""
    async with SessionFactory() as session:
        bots, created = await seed_demo(
            session, embedder=FakeEmbedder(), email="demo@example.com", password="Demo1234pass"
        )
        return {b.language: b.public_key for b in bots}, created


async def test_seed_creates_a_demo_bot_with_ready_sources() -> None:
    _, created = await _seed()
    assert created is True
    async with SessionFactory() as session:
        statuses = set(await session.scalars(select(Source.status)))
        chunks = await session.scalar(select(func.count()).select_from(Chunk))
    assert statuses == {SourceStatus.READY}
    assert (chunks or 0) >= sum(len(a.documents) for a in DEMO_ASSISTANTS)


async def test_seed_is_idempotent() -> None:
    first_key, _ = await _seed()
    second_key, created = await _seed()
    assert second_key == first_key
    assert created is False
    async with SessionFactory() as session:
        sources = await session.scalar(select(func.count()).select_from(Source))
    assert sources == sum(len(a.documents) for a in DEMO_ASSISTANTS)


async def test_demo_assistant_answers_from_its_documents(client: AsyncClient) -> None:
    keys, _ = await _seed()
    events = parse_sse(
        await _ask(client, keys["en"], "refunds go back to the original payment method")
    )
    citations = dict(events)["citations"]
    assert citations[0]["source_name"] == "returns-and-refunds.md"
    assert dict(events)["done"] == {"answered": True}


async def test_the_catalogue_question_the_demo_suggests_gets_an_answer(
    client: AsyncClient,
) -> None:
    keys, _ = await _seed()
    for language, question, source in (
        ("en", "What can I order?", "products.md"),
        ("es", "¿Qué puedo pedir?", "productos.md"),
    ):
        events = dict(parse_sse(await _ask(client, keys[language], question)))
        assert events["citations"][0]["source_name"] == source


async def test_seeding_again_refreshes_the_demo_settings(client: AsyncClient) -> None:
    keys, _ = await _seed()
    config = (await client.get(f"/public/bots/{keys['es']}")).json()
    assert config["language"] == "es"
    assert len(config["suggested_questions"]) == 4
