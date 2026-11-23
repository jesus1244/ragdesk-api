"""Text embeddings behind a small protocol, so tests and offline development need no API key.

`gemini-embedding-2` does not take a `task_type`. Instead the task is written into the text with a
prefix, and each text must be its own `Content` (a plain list of strings would be merged into one
embedding).
"""

import hashlib
import math
import re
from collections.abc import Sequence
from typing import Protocol

from google import genai
from google.genai import types

from ragdesk.core.config import EMBEDDING_DIMENSIONS, get_settings

GEMINI_BATCH_SIZE = 50
_WORD = re.compile(r"\w+", re.UNICODE)


class EmbeddingError(Exception):
    """The provider failed or returned something unusable."""


class Embedder(Protocol):
    async def embed_documents(self, items: Sequence[tuple[str, str]]) -> list[list[float]]:
        """Embed `(title, text)` pairs, returning one vector per pair in the same order."""
        ...

    async def embed_query(self, text: str) -> list[float]: ...


def document_text(title: str, text: str) -> str:
    return f"title: {title or 'none'} | text: {text}"


def query_text(text: str) -> str:
    return f"task: search result | query: {text}"


class GeminiEmbedder:
    def __init__(
        self, client: genai.Client, model: str, dimensions: int = EMBEDDING_DIMENSIONS
    ) -> None:
        self._client = client
        self._model = model
        self._config = types.EmbedContentConfig(output_dimensionality=dimensions)
        self._dimensions = dimensions

    async def _embed(self, texts: Sequence[str]) -> list[list[float]]:
        contents = [types.Content(parts=[types.Part.from_text(text=t)]) for t in texts]
        try:
            result = await self._client.aio.models.embed_content(
                model=self._model, contents=contents, config=self._config
            )
        except Exception as exc:  # the SDK raises several provider-specific error types
            raise EmbeddingError(f"Embedding request failed: {type(exc).__name__}") from exc
        vectors = [list(e.values or []) for e in result.embeddings or []]
        if len(vectors) != len(texts) or any(len(v) != self._dimensions for v in vectors):
            raise EmbeddingError("Embedding provider returned an unexpected shape")
        return vectors

    async def embed_documents(self, items: Sequence[tuple[str, str]]) -> list[list[float]]:
        texts = [document_text(title, text) for title, text in items]
        vectors: list[list[float]] = []
        for start in range(0, len(texts), GEMINI_BATCH_SIZE):
            vectors.extend(await self._embed(texts[start : start + GEMINI_BATCH_SIZE]))
        return vectors

    async def embed_query(self, text: str) -> list[float]:
        return (await self._embed([query_text(text)]))[0]


class FakeEmbedder:
    """Deterministic bag-of-words embedder: texts that share words get a high cosine similarity."""

    def __init__(self, dimensions: int = EMBEDDING_DIMENSIONS) -> None:
        self._dimensions = dimensions

    def _vector(self, text: str) -> list[float]:
        vector = [0.0] * self._dimensions
        for word in _WORD.findall(text.lower()):
            digest = hashlib.blake2b(word.encode(), digest_size=4).digest()
            vector[int.from_bytes(digest, "big") % self._dimensions] += 1.0
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]

    async def embed_documents(self, items: Sequence[tuple[str, str]]) -> list[list[float]]:
        return [self._vector(f"{title} {text}") for title, text in items]

    async def embed_query(self, text: str) -> list[float]:
        return self._vector(text)


_embedder: Embedder | None = None


def get_embedder() -> Embedder:
    global _embedder  # noqa: PLW0603 - process-wide provider client
    if _embedder is None:
        settings = get_settings()
        if settings.embedder == "gemini":
            if settings.gemini_api_key is None:
                raise EmbeddingError("GEMINI_API_KEY is not configured")
            client = genai.Client(
                api_key=settings.gemini_api_key.get_secret_value(),
                http_options=types.HttpOptions(timeout=30_000),
            )
            _embedder = GeminiEmbedder(client, settings.gemini_embedding_model)
        else:
            _embedder = FakeEmbedder()
    return _embedder


def set_embedder(embedder: Embedder | None) -> None:
    """Swap the embedder (used by tests)."""
    global _embedder  # noqa: PLW0603
    _embedder = embedder
