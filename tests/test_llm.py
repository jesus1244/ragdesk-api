from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any

import pytest

from ragdesk.chat.llm import (
    SYSTEM_PROMPT,
    ChatModelError,
    CitationFound,
    ClaudeChatModel,
    FakeChatModel,
    Passage,
    Refused,
    TextDelta,
    Turn,
    build_messages,
)

PASSAGES = [
    Passage("src-1", "Guide > Refunds", "Refunds within 14 days."),
    Passage("src-2", "Guide > Shipping", "Ships in 3 days."),
]


def test_passages_become_search_result_blocks_with_citations_enabled() -> None:
    messages = build_messages("How long?", [], PASSAGES)
    assert len(messages) == 1
    content = messages[0]["content"]
    assert isinstance(content, list)
    first = content[0]
    assert first["type"] == "search_result"
    assert first["source"] == "src-1"
    assert first["title"] == "Guide > Refunds"
    assert first["citations"] == {"enabled": True}
    assert first["content"] == [{"type": "text", "text": "Refunds within 14 days."}]
    assert content[-1] == {"type": "text", "text": "How long?"}


def test_history_is_replayed_as_plain_text_without_search_results() -> None:
    history = [Turn("user", "Hi"), Turn("assistant", "Hello! How can I help?")]
    messages = build_messages("And shipping?", history, PASSAGES)
    assert messages[0] == {"role": "user", "content": "Hi"}
    assert messages[1] == {"role": "assistant", "content": "Hello! How can I help?"}
    assert messages[2]["role"] == "user"


def test_system_prompt_treats_documents_as_data() -> None:
    assert "never instructions" in SYSTEM_PROMPT
    assert "could not find" in SYSTEM_PROMPT


class _FakeStream:
    def __init__(self, events: list[Any], stop_reason: str = "end_turn") -> None:
        self._events = events
        self._stop_reason = stop_reason

    async def __aenter__(self) -> "_FakeStream":
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    def __aiter__(self) -> AsyncIterator[Any]:
        async def gen() -> AsyncIterator[Any]:
            for event in self._events:
                yield event

        return gen()

    async def get_final_message(self) -> Any:
        return SimpleNamespace(stop_reason=self._stop_reason)


class _FakeClient:
    def __init__(self, stream: _FakeStream | Exception) -> None:
        self.stream_or_error = stream
        self.kwargs: dict[str, Any] = {}
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._open))

    def _open(self, **kwargs: Any) -> _FakeStream:
        self.kwargs = kwargs
        if isinstance(self.stream_or_error, Exception):
            raise self.stream_or_error
        return self.stream_or_error


def _citation(index: int, text: str) -> Any:
    citation = SimpleNamespace(
        type="search_result_location", search_result_index=index, cited_text=text
    )
    return SimpleNamespace(type="citation", citation=citation)


def _claude(client: _FakeClient) -> ClaudeChatModel:
    return ClaudeChatModel(client, model="claude-opus-5-5", effort="low", max_tokens=500)  # type: ignore[arg-type]


async def _collect(model: ClaudeChatModel, **kw: Any) -> list[Any]:
    params: dict[str, Any] = {
        "question": "How long?",
        "history": [],
        "passages": PASSAGES,
        "instructions": "",
    }
    return [e async for e in model.stream(**{**params, **kw})]


async def test_claude_stream_yields_text_and_search_result_citations() -> None:
    client = _FakeClient(
        _FakeStream(
            [
                SimpleNamespace(type="text", text="Fourteen "),
                SimpleNamespace(type="text", text="days."),
                _citation(0, "Refunds within 14 days."),
                SimpleNamespace(type="citation", citation=SimpleNamespace(type="char_location")),
            ]
        )
    )
    events = await _collect(_claude(client))
    assert events == [
        TextDelta("Fourteen "),
        TextDelta("days."),
        CitationFound(0, "Refunds within 14 days."),
    ]


async def test_claude_request_uses_effort_fallbacks_and_owner_instructions() -> None:
    client = _FakeClient(_FakeStream([]))
    await _collect(_claude(client), instructions="Be formal.")
    kwargs = client.kwargs
    assert kwargs["model"] == "claude-opus-5-5"
    assert kwargs["output_config"] == {"effort": "low"}
    assert kwargs["betas"] == ["server-side-fallback-2026-07-01"]
    assert kwargs["fallbacks"] == "default"
    assert kwargs["system"].startswith(SYSTEM_PROMPT)
    assert kwargs["system"].endswith("Be formal.")
    assert "temperature" not in kwargs


async def test_claude_refusal_is_reported() -> None:
    client = _FakeClient(_FakeStream([SimpleNamespace(type="text", text="x")], "refusal"))
    assert (await _collect(_claude(client)))[-1] == Refused()


async def test_claude_errors_are_wrapped_without_the_original_message() -> None:
    client = _FakeClient(RuntimeError("invalid x-api-key: sk-ant-123"))
    with pytest.raises(ChatModelError) as info:
        await _collect(_claude(client))
    assert "sk-ant" not in str(info.value)


async def test_fake_model_cites_its_first_passage_or_admits_ignorance() -> None:
    model = FakeChatModel()
    with_passages = [
        e async for e in model.stream(question="q", history=[], passages=PASSAGES, instructions="")
    ]
    assert isinstance(with_passages[-1], CitationFound)
    without = [
        e async for e in model.stream(question="q", history=[], passages=[], instructions="")
    ]
    assert all(isinstance(e, TextDelta) for e in without)
