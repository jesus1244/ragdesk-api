import math
from types import SimpleNamespace
from typing import Any

import pytest

from ragdesk.core.config import EMBEDDING_DIMENSIONS
from ragdesk.core.embeddings import (
    EmbeddingError,
    FakeEmbedder,
    GeminiEmbedder,
    document_text,
    query_text,
)


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


async def test_fake_embedder_is_deterministic_and_normalised() -> None:
    embedder = FakeEmbedder()
    first = await embedder.embed_query("reset my password")
    second = await embedder.embed_query("reset my password")
    assert first == second
    assert len(first) == EMBEDDING_DIMENSIONS
    assert math.isclose(math.sqrt(sum(v * v for v in first)), 1.0, rel_tol=1e-9)


async def test_fake_embedder_ranks_texts_that_share_words_higher() -> None:
    embedder = FakeEmbedder()
    query = await embedder.embed_query("how do I reset my password")
    docs = await embedder.embed_documents(
        [
            ("Account", "To reset your password open the settings page."),
            ("Billing", "Invoices are sent on the first day of each month."),
        ]
    )
    assert _cosine(query, docs[0]) > _cosine(query, docs[1])


def test_prefixes_follow_the_gemini_embedding_2_format() -> None:
    assert query_text("hi") == "task: search result | query: hi"
    assert document_text("Guide", "body") == "title: Guide | text: body"
    assert document_text("", "body") == "title: none | text: body"


class _FakeGeminiModels:
    def __init__(self, dimensions: int, *, drop_one: bool = False, fail: bool = False) -> None:
        self.dimensions = dimensions
        self.drop_one = drop_one
        self.fail = fail
        self.calls: list[list[str]] = []

    async def embed_content(self, *, model: str, contents: list[Any], config: Any) -> Any:
        if self.fail:
            raise RuntimeError("boom")
        self.calls.append([c.parts[0].text for c in contents])
        count = len(contents) - (1 if self.drop_one else 0)
        embeddings = [SimpleNamespace(values=[0.1] * self.dimensions) for _ in range(count)]
        return SimpleNamespace(embeddings=embeddings)


def _gemini(models: _FakeGeminiModels) -> GeminiEmbedder:
    client = SimpleNamespace(aio=SimpleNamespace(models=models))
    return GeminiEmbedder(client, "gemini-embedding-2", EMBEDDING_DIMENSIONS)  # type: ignore[arg-type]


async def test_gemini_embedder_batches_and_sends_prefixed_texts() -> None:
    models = _FakeGeminiModels(EMBEDDING_DIMENSIONS)
    items = [(f"T{i}", f"text {i}") for i in range(120)]
    vectors = await _gemini(models).embed_documents(items)
    assert len(vectors) == 120
    assert [len(batch) for batch in models.calls] == [50, 50, 20]
    assert models.calls[0][0] == "title: T0 | text: text 0"


async def test_gemini_embedder_rejects_a_wrong_number_of_vectors() -> None:
    with pytest.raises(EmbeddingError, match="unexpected shape"):
        await _gemini(_FakeGeminiModels(EMBEDDING_DIMENSIONS, drop_one=True)).embed_documents(
            [("a", "b"), ("c", "d")]
        )


async def test_gemini_embedder_rejects_a_wrong_dimension() -> None:
    with pytest.raises(EmbeddingError, match="unexpected shape"):
        await _gemini(_FakeGeminiModels(3)).embed_query("hello")


async def test_gemini_embedder_wraps_provider_errors_without_leaking_details() -> None:
    with pytest.raises(EmbeddingError) as info:
        await _gemini(_FakeGeminiModels(EMBEDDING_DIMENSIONS, fail=True)).embed_query("hello")
    assert "boom" not in str(info.value)
