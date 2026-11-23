"""Hybrid retrieval: vector search and full-text search, fused with Reciprocal Rank Fusion.

- The vector query ranks chunks by cosine distance (HNSW index).
- The keyword query ranks chunks that contain any of the question's words (GIN index). It catches
  exact tokens such as error codes and product names that embeddings blur.
- Reciprocal Rank Fusion scores each chunk as the sum of 1 / (K + rank) over the lists it appears
  in, so no score normalisation between the two lists is needed.
- Finally a chunk must be semantically close enough (`max_distance`). Keyword matches reorder the
  candidates but cannot pull in a passage the embedding finds unrelated.

Every query filters by `bot_id`: that filter is the tenant boundary.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import Row, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ragdesk.core.embeddings import Embedder
from ragdesk.sources.models import Chunk, Source

RRF_K = 60
MAX_QUERY_WORDS = 12
MAX_QUERY_CHARS = 1000
_WORD = re.compile(r"\w{2,}", re.UNICODE)
_STOPWORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "can",
        "do",
        "does",
        "for",
        "from",
        "has",
        "have",
        "how",
        "i",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "that",
        "the",
        "this",
        "to",
        "was",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "with",
        "you",
        "your",
        "al",
        "como",
        "con",
        "cual",
        "cuando",
        "de",
        "del",
        "el",
        "en",
        "es",
        "la",
        "las",
        "lo",
        "los",
        "me",
        "mi",
        "para",
        "por",
        "que",
        "se",
        "si",
        "su",
        "un",
        "una",
        "y",
    ]
)


@dataclass(frozen=True, slots=True)
class Hit:
    chunk_id: UUID
    source_id: UUID
    source_name: str
    title: str
    content: str
    distance: float
    score: float


def keyword_query(question: str) -> str:
    """Turn a question into an OR query for `websearch_to_tsquery`, dropping stopwords."""
    words = [w for w in _WORD.findall(question.lower()) if w not in _STOPWORDS]
    return " or ".join(dict.fromkeys(words[:MAX_QUERY_WORDS]))


def rrf_fuse(*rankings: list[UUID]) -> dict[UUID, float]:
    """Reciprocal Rank Fusion over any number of ranked id lists (best first)."""
    scores: dict[UUID, float] = {}
    for ranking in rankings:
        for rank, chunk_id in enumerate(ranking, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (RRF_K + rank)
    return scores


async def search(
    session: AsyncSession,
    bot_id: UUID,
    question: str,
    *,
    embedder: Embedder,
    top_k: int,
    candidates: int,
    max_distance: float,
) -> list[Hit]:
    question = question.strip()[:MAX_QUERY_CHARS]
    if not question:
        return []
    vector = await embedder.embed_query(question)
    distance = Chunk.embedding.cosine_distance(vector).label("distance")
    columns = (Chunk.id, Chunk.source_id, Source.name, Chunk.title, Chunk.content, distance)

    # Keep scanning the HNSW index until enough rows pass the tenant filter.
    await session.execute(text("SET LOCAL hnsw.iterative_scan = strict_order"))
    await session.execute(text("SET LOCAL hnsw.ef_search = 100"))
    vector_rows = (
        await session.execute(
            select(*columns)
            .join(Source, Source.id == Chunk.source_id)
            .where(Chunk.bot_id == bot_id)
            .order_by(distance)
            .limit(candidates)
        )
    ).all()

    keyword_rows: Sequence[Row[Any]] = []
    if tsquery := keyword_query(question):
        query = func.websearch_to_tsquery("simple", tsquery)
        keyword_rows = (
            await session.execute(
                select(*columns)
                .join(Source, Source.id == Chunk.source_id)
                .where(Chunk.bot_id == bot_id, Chunk.search.op("@@")(query))
                .order_by(func.ts_rank_cd(Chunk.search, query).desc())
                .limit(candidates)
            )
        ).all()

    rows = {row.id: row for row in [*keyword_rows, *vector_rows]}
    scores = rrf_fuse([r.id for r in vector_rows], [r.id for r in keyword_rows])
    ranked = sorted(scores, key=lambda chunk_id: scores[chunk_id], reverse=True)
    hits = [
        Hit(
            chunk_id=row.id,
            source_id=row.source_id,
            source_name=row.name,
            title=row.title,
            content=row.content,
            distance=float(row.distance),
            score=scores[row.id],
        )
        for row in (rows[chunk_id] for chunk_id in ranked)
        if row.distance <= max_distance
    ]
    return hits[:top_k]
