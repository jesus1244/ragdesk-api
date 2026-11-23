import json
from collections.abc import AsyncIterator, Sequence
from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import select

from ragdesk.chat.llm import (
    ChatEvent,
    ChatModelError,
    CitationFound,
    Passage,
    Refused,
    TextDelta,
    Turn,
    set_chat_model,
)
from ragdesk.chat.models import Message
from ragdesk.core.database import SessionFactory
from tests.conftest import register_and_login

DOC = b"""# Support

## Refunds

Customers can request a refund within fourteen days of purchase.

## Shipping

Orders ship from our warehouse in three business days.
"""


class RecordingModel:
    """A chat model double that records its calls and plays back scripted events."""

    def __init__(self, events: Sequence[ChatEvent] | Exception | None = None) -> None:
        self.events = events
        self.calls: list[dict[str, Any]] = []

    async def stream(
        self,
        *,
        question: str,
        history: Sequence[Turn],
        passages: Sequence[Passage],
        instructions: str,
    ) -> AsyncIterator[ChatEvent]:
        self.calls.append(
            {
                "question": question,
                "history": list(history),
                "passages": list(passages),
                "instructions": instructions,
            }
        )
        if isinstance(self.events, Exception):
            raise self.events
        for event in self.events or [TextDelta("ok")]:
            yield event


def parse_sse(response: Response) -> list[tuple[str, Any]]:
    events: list[tuple[str, Any]] = []
    for block in response.text.split("\n\n"):
        name, data = "message", ""
        for line in block.splitlines():
            if line.startswith("event:"):
                name = line.removeprefix("event:").strip()
            elif line.startswith("data:"):
                data += line.removeprefix("data:").strip()
        if data:
            events.append((name, json.loads(data)))
    return events


async def _bot(client: AsyncClient, headers: dict[str, str], **extra: Any) -> tuple[str, str]:
    created = (
        await client.post("/bots", json={"name": "Support", **extra}, headers=headers)
    ).json()
    await client.post(
        f"/bots/{created['id']}/sources/file", files={"file": ("doc.md", DOC)}, headers=headers
    )
    return created["id"], created["public_key"]


async def _ask(
    client: AsyncClient,
    key: str,
    question: str,
    *,
    conversation_id: str | None = None,
    origin: str | None = None,
) -> Response:
    body: dict[str, Any] = {"question": question}
    if conversation_id:
        body["conversation_id"] = conversation_id
    headers = {"Origin": origin} if origin else {}
    return await client.post(f"/public/chat/{key}", json=body, headers=headers)


async def _messages() -> list[Message]:
    async with SessionFactory() as session:
        return list((await session.scalars(select(Message).order_by(Message.created_at))).all())


async def test_a_sourced_answer_streams_text_then_citations(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    _, key = await _bot(client, auth_headers)
    response = await _ask(client, key, "refund within fourteen days of purchase")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    events = parse_sse(response)
    names = [name for name, _ in events]
    assert names[0] == "meta"
    assert "delta" in names
    assert names[-2:] == ["citations", "done"]

    text = "".join(d["text"] for n, d in events if n == "delta")
    assert "fourteen days" in text
    citations = dict(events)["citations"]
    assert citations[0]["index"] == 1
    assert citations[0]["source_name"] == "doc.md"
    assert citations[0]["title"] == "Support > Refunds"
    assert dict(events)["done"] == {"answered": True}


async def test_both_sides_of_the_exchange_are_stored(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    _, key = await _bot(client, auth_headers)
    await _ask(client, key, "refund within fourteen days of purchase")
    user, assistant = await _messages()
    assert (user.role, user.content) == ("user", "refund within fourteen days of purchase")
    assert assistant.role == "assistant"
    assert assistant.answered is True
    assert assistant.question == "refund within fourteen days of purchase"
    assert assistant.citations[0]["title"] == "Support > Refunds"


async def test_unrelated_questions_skip_the_model_and_count_as_unanswered(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    model = RecordingModel()
    set_chat_model(model)
    try:
        _, key = await _bot(client, auth_headers)
        events = parse_sse(await _ask(client, key, "quantum chromodynamics lagrangian"))
    finally:
        set_chat_model(None)

    assert model.calls == []  # no passages, so no paid call
    assert dict(events)["done"] == {"answered": False}
    assert dict(events)["citations"] == []
    assert "could not find" in "".join(d["text"] for n, d in events if n == "delta")
    assert (await _messages())[-1].answered is False


async def test_the_model_receives_retrieved_passages_and_owner_instructions(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    model = RecordingModel([TextDelta("Fourteen days. "), CitationFound(0, "refund within")])
    set_chat_model(model)
    try:
        _, key = await _bot(client, auth_headers, instructions="Answer formally.")
        await _ask(client, key, "customers request a refund within fourteen days")
    finally:
        set_chat_model(None)

    call = model.calls[0]
    assert call["instructions"] == "Answer formally."
    assert call["passages"][0].title == "Support > Refunds"
    assert "fourteen days" in call["passages"][0].text


async def test_follow_up_questions_carry_the_conversation_history(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    model = RecordingModel([TextDelta("Fourteen days."), CitationFound(0, "x")])
    set_chat_model(model)
    try:
        _, key = await _bot(client, auth_headers)
        first = parse_sse(
            await _ask(client, key, "customers request a refund within fourteen days")
        )
        conversation_id = dict(first)["meta"]["conversation_id"]
        await _ask(
            client,
            key,
            "orders ship from our warehouse in three business days",
            conversation_id=conversation_id,
        )
    finally:
        set_chat_model(None)

    assert model.calls[0]["history"] == []
    assert model.calls[1]["history"] == [
        Turn("user", "customers request a refund within fourteen days"),
        Turn("assistant", "Fourteen days."),
    ]


async def test_citations_pointing_at_unknown_passages_are_ignored_and_duplicates_merged(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    set_chat_model(
        RecordingModel(
            [TextDelta("x"), CitationFound(0, "a"), CitationFound(0, "b"), CitationFound(99, "c")]
        )
    )
    try:
        _, key = await _bot(client, auth_headers)
        events = parse_sse(await _ask(client, key, "refund within fourteen days"))
    finally:
        set_chat_model(None)
    assert len(dict(events)["citations"]) == 1


async def test_an_answer_without_citations_is_unanswered(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    set_chat_model(RecordingModel([TextDelta("I am not sure about that.")]))
    try:
        _, key = await _bot(client, auth_headers)
        events = parse_sse(await _ask(client, key, "refund within fourteen days"))
    finally:
        set_chat_model(None)
    assert dict(events)["done"] == {"answered": False}


async def test_a_refusal_is_reported_politely_and_is_unanswered(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    set_chat_model(RecordingModel([TextDelta("partial"), CitationFound(0, "x"), Refused()]))
    try:
        _, key = await _bot(client, auth_headers)
        events = parse_sse(await _ask(client, key, "refund within fourteen days"))
    finally:
        set_chat_model(None)
    assert dict(events)["done"] == {"answered": False}
    assert dict(events)["citations"] == []
    assert (await _messages())[-1].content == "Sorry, I cannot help with that request."


async def test_a_provider_failure_becomes_an_error_event_without_details(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    set_chat_model(RecordingModel(ChatModelError("api key sk-secret rejected")))
    try:
        _, key = await _bot(client, auth_headers)
        response = await _ask(client, key, "refund within fourteen days")
    finally:
        set_chat_model(None)
    events = parse_sse(response)
    assert events[-1][0] == "error"
    assert "sk-secret" not in response.text
    assert "citations" not in dict(events)
    assert [m.role for m in await _messages()] == ["user"]


async def test_unknown_assistant_is_a_404(client: AsyncClient) -> None:
    response = await _ask(client, "bot_does_not_exist", "hello")
    assert response.status_code == 404


async def test_deleted_bot_stops_answering(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    bot_id, key = await _bot(client, auth_headers)
    await client.delete(f"/bots/{bot_id}", headers=auth_headers)
    assert (await _ask(client, key, "hello")).status_code == 404


async def test_origin_must_match_the_allowed_list_when_one_is_set(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    _, key = await _bot(client, auth_headers, allowed_origins=["https://shop.example.com"])
    assert (await _ask(client, key, "hello")).status_code == 403
    assert (await _ask(client, key, "hello", origin="https://evil.example.com")).status_code == 403
    allowed = await _ask(
        client, key, "refund within fourteen days", origin="https://shop.example.com"
    )
    assert allowed.status_code == 200


async def test_without_an_allowed_list_any_website_may_embed_the_widget(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    _, key = await _bot(client, auth_headers)
    response = await _ask(client, key, "hello", origin="https://anywhere.example.org")
    assert response.status_code == 200


async def test_a_conversation_of_another_bot_is_a_404(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    _, key_a = await _bot(client, auth_headers)
    other = await register_and_login(client, email="bob@example.com")
    _, key_b = await _bot(client, other)
    conversation_id = dict(parse_sse(await _ask(client, key_a, "hello")))["meta"]["conversation_id"]

    assert (await _ask(client, key_b, "hi", conversation_id=conversation_id)).status_code == 404
    assert (await _ask(client, key_b, "hi", conversation_id=str(uuid4()))).status_code == 404


async def test_invalid_questions_are_rejected(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    _, key = await _bot(client, auth_headers)
    assert (await _ask(client, key, "")).status_code == 422
    assert (await _ask(client, key, "x" * 1001)).status_code == 422


async def test_widget_config_exposes_only_name_and_welcome_message(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    _, key = await _bot(client, auth_headers, instructions="secret guidance")
    response = await client.get(f"/public/bots/{key}")
    assert response.status_code == 200
    assert set(response.json()) == {"name", "welcome_message"}


@pytest.mark.parametrize("path", ["/public/chat/bot_x", "/public/bots/bot_x"])
async def test_cors_preflight_is_answered_for_any_origin_on_public_paths(
    client: AsyncClient, path: str
) -> None:
    response = await client.options(
        path,
        headers={"Origin": "https://shop.example.com", "Access-Control-Request-Method": "POST"},
    )
    assert response.status_code == 204
    assert response.headers["access-control-allow-origin"] == "https://shop.example.com"
    assert "access-control-allow-credentials" not in response.headers


async def test_cors_headers_are_present_on_public_responses_and_absent_on_admin_ones(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    _, key = await _bot(client, auth_headers)
    public = await client.get(f"/public/bots/{key}", headers={"Origin": "https://a.example.com"})
    assert public.headers["access-control-allow-origin"] == "https://a.example.com"
    admin = await client.get("/bots", headers={**auth_headers, "Origin": "https://a.example.com"})
    assert "access-control-allow-origin" not in admin.headers
