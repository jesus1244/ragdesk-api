from typing import Any
from uuid import uuid4

from httpx import AsyncClient

from tests.conftest import register_and_login
from tests.test_chat import _ask, _bot, parse_sse

ANSWERABLE = "refund within fourteen days of purchase"
UNANSWERABLE = "quantum chromodynamics lagrangian"


async def _conversation(client: AsyncClient, key: str, question: str) -> str:
    events = parse_sse(await _ask(client, key, question))
    return str(dict(events)["meta"]["conversation_id"])


async def test_stats_count_answered_and_unanswered_questions(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    bot_id, key = await _bot(client, auth_headers)
    await _conversation(client, key, ANSWERABLE)
    await _conversation(client, key, UNANSWERABLE)
    await _conversation(client, key, UNANSWERABLE)

    stats = (await client.get(f"/bots/{bot_id}/stats", headers=auth_headers)).json()
    assert stats == {
        "conversations": 3,
        "questions": 3,
        "answered": 1,
        "unanswered": 2,
        "answer_rate": 0.333,
    }


async def test_stats_of_a_new_bot_are_zero(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    created = (await client.post("/bots", json={"name": "Empty"}, headers=auth_headers)).json()
    stats = (await client.get(f"/bots/{created['id']}/stats", headers=auth_headers)).json()
    assert stats["questions"] == 0
    assert stats["answer_rate"] == 0.0


async def test_conversations_are_listed_with_their_first_question_and_paginated(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    bot_id, key = await _bot(client, auth_headers)
    await _conversation(client, key, ANSWERABLE)
    await _conversation(client, key, UNANSWERABLE)

    page = (await client.get(f"/bots/{bot_id}/conversations", headers=auth_headers)).json()
    assert page["total"] == 2
    assert page["items"][0]["last_question"] == UNANSWERABLE  # most recent first
    assert page["items"][0]["message_count"] == 2

    second = (
        await client.get(
            f"/bots/{bot_id}/conversations", params={"limit": 1, "offset": 1}, headers=auth_headers
        )
    ).json()
    assert [i["last_question"] for i in second["items"]] == [ANSWERABLE]


async def test_conversation_messages_include_citations_in_order(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    bot_id, key = await _bot(client, auth_headers)
    conversation_id = await _conversation(client, key, ANSWERABLE)

    response = await client.get(
        f"/bots/{bot_id}/conversations/{conversation_id}/messages", headers=auth_headers
    )
    messages: list[dict[str, Any]] = response.json()
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[1]["answered"] is True
    assert messages[1]["citations"][0]["title"] == "Support > Refunds"


async def test_unanswered_questions_are_listed_newest_first(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    bot_id, key = await _bot(client, auth_headers)
    await _conversation(client, key, ANSWERABLE)
    await _conversation(client, key, UNANSWERABLE)

    page = (await client.get(f"/bots/{bot_id}/unanswered", headers=auth_headers)).json()
    assert page["total"] == 1
    assert page["items"][0]["question"] == UNANSWERABLE


async def test_another_owner_gets_404_everywhere(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    bot_id, key = await _bot(client, auth_headers)
    conversation_id = await _conversation(client, key, ANSWERABLE)
    other = await register_and_login(client, email="bob@example.com")

    for path in (
        f"/bots/{bot_id}/stats",
        f"/bots/{bot_id}/conversations",
        f"/bots/{bot_id}/unanswered",
        f"/bots/{bot_id}/conversations/{conversation_id}/messages",
    ):
        assert (await client.get(path, headers=other)).status_code == 404
        assert (await client.get(path)).status_code == 401


async def test_unknown_conversation_is_404(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    bot_id, _ = await _bot(client, auth_headers)
    response = await client.get(
        f"/bots/{bot_id}/conversations/{uuid4()}/messages", headers=auth_headers
    )
    assert response.status_code == 404
