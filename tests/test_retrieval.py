from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient

from ragdesk.core.database import SessionFactory
from ragdesk.core.embeddings import get_embedder
from ragdesk.retrieval.service import Hit, keyword_query, rrf_fuse, search
from tests.conftest import register_and_login

POLICY = b"""# Policies

## Refunds

Customers can request a refund within fourteen days of purchase.
Refunds are paid to the original card.

## Shipping

Orders ship from our warehouse in three business days. Express shipping is available.

## Error codes

Error ERR-4021 means the payment provider rejected the card. Contact your bank.
"""

COOKING = b"""# Pasta

## Sauce

Simmer the tomatoes with garlic and basil for twenty minutes before adding the pasta.
"""


async def _bot_with(client: AsyncClient, headers: dict[str, str], doc: bytes) -> UUID:
    bot_id = (await client.post("/bots", json={"name": "Bot"}, headers=headers)).json()["id"]
    await client.post(
        f"/bots/{bot_id}/sources/file", files={"file": ("doc.md", doc)}, headers=headers
    )
    return UUID(bot_id)


async def _search(bot_id: UUID, question: str, *, max_distance: float = 0.95) -> list[Hit]:
    async with SessionFactory() as session:
        return await search(
            session,
            bot_id,
            question,
            embedder=get_embedder(),
            top_k=3,
            candidates=20,
            max_distance=max_distance,
        )


def test_rrf_rewards_chunks_found_by_both_searches() -> None:
    a, b, c = uuid4(), uuid4(), uuid4()
    scores = rrf_fuse([a, b], [b, c])
    assert max(scores, key=lambda k: scores[k]) == b
    assert scores[a] > scores[c]  # rank 1 in one list beats rank 2 in the other


def test_rrf_with_one_empty_list_keeps_the_other_order() -> None:
    a, b = uuid4(), uuid4()
    scores = rrf_fuse([a, b], [])
    assert scores[a] > scores[b]


def test_keyword_query_drops_stopwords_and_joins_with_or() -> None:
    assert keyword_query("What is the refund policy?") == "refund or policy"
    assert keyword_query("how do I fix ERR-4021") == "fix or err or 4021"
    assert keyword_query("the of a") == ""
    assert keyword_query("") == ""


async def test_the_most_relevant_passage_comes_first(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    bot_id = await _bot_with(client, auth_headers, POLICY)
    hits = await _search(bot_id, "Can I get a refund after purchase?")
    assert hits
    assert hits[0].title == "Policies > Refunds"
    assert "fourteen days" in hits[0].content
    assert hits[0].source_name == "doc.md"


async def test_exact_tokens_are_found_by_keyword_search(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    bot_id = await _bot_with(client, auth_headers, POLICY)
    hits = await _search(bot_id, "ERR-4021")
    assert hits[0].title == "Policies > Error codes"


async def test_results_never_cross_bots(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    mine = await _bot_with(client, auth_headers, POLICY)
    other_headers = await register_and_login(client, email="bob@example.com")
    theirs = await _bot_with(client, other_headers, COOKING)

    assert all("tomatoes" not in h.content for h in await _search(mine, "tomato garlic sauce"))
    their_hits = await _search(theirs, "refund policy")
    assert all("refund" not in h.content.lower() for h in their_hits)
    assert (await _search(theirs, "tomato sauce"))[0].title == "Pasta > Sauce"


async def test_unrelated_questions_return_nothing_under_a_strict_threshold(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    bot_id = await _bot_with(client, auth_headers, POLICY)
    assert await _search(bot_id, "quantum chromodynamics lagrangian", max_distance=0.7) == []


async def test_blank_question_and_empty_bot_return_nothing(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    empty = (await client.post("/bots", json={"name": "Empty"}, headers=auth_headers)).json()["id"]
    assert await _search(UUID(empty), "anything at all") == []
    assert await _search(UUID(empty), "   ") == []


async def test_top_k_limits_the_results(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    bot_id = await _bot_with(client, auth_headers, POLICY)
    async with SessionFactory() as session:
        hits = await search(
            session,
            bot_id,
            "refund shipping error card orders",
            embedder=get_embedder(),
            top_k=2,
            candidates=20,
            max_distance=1.0,
        )
    assert len(hits) == 2
    assert hits[0].score >= hits[1].score


@pytest.mark.parametrize(
    "question", ["'; DROP TABLE chunk; --", "refund & (shipping | !card)", "\x00"]
)
async def test_hostile_questions_do_not_break_the_search(
    client: AsyncClient, auth_headers: dict[str, str], question: str
) -> None:
    bot_id = await _bot_with(client, auth_headers, POLICY)
    await _search(bot_id, question.replace("\x00", ""))
    assert await _search(bot_id, "refund")
