from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import Computed, ForeignKey, Index, LargeBinary, String, Text
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, deferred, mapped_column

from ragdesk.core.config import EMBEDDING_DIMENSIONS
from ragdesk.core.database import Base, TimestampMixin, UUIDPrimaryKeyMixin


class SourceKind(StrEnum):
    FILE = "file"
    URL = "url"
    TEXT = "text"


class SourceStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class Source(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A document, web page or pasted text that belongs to a bot."""

    __tablename__ = "source"

    bot_id: Mapped[UUID] = mapped_column(ForeignKey("bot.id", ondelete="CASCADE"), index=True)
    kind: Mapped[SourceKind] = mapped_column(String(10))
    name: Mapped[str] = mapped_column(String(255))
    url: Mapped[str | None] = mapped_column(String(2048))
    content_type: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[SourceStatus] = mapped_column(String(12), default=SourceStatus.PENDING)
    error: Mapped[str | None] = mapped_column(String(500))
    chunk_count: Mapped[int] = mapped_column(default=0)
    # Raw upload kept only until ingestion succeeds, then cleared.
    raw: Mapped[bytes | None] = deferred(mapped_column(LargeBinary))


class Chunk(Base):
    """A passage of a source with its embedding; `bot_id` is denormalised for scoped search."""

    __tablename__ = "chunk"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_id: Mapped[UUID] = mapped_column(ForeignKey("source.id", ondelete="CASCADE"), index=True)
    bot_id: Mapped[UUID] = mapped_column(ForeignKey("bot.id", ondelete="CASCADE"), index=True)
    position: Mapped[int]
    title: Mapped[str] = mapped_column(String(300))
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[Any] = mapped_column(Vector(EMBEDDING_DIMENSIONS))
    search: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('simple', title || ' ' || content)", persisted=True),
    )

    __table_args__ = (
        Index(
            "chunk_embedding_hnsw_idx",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("chunk_search_gin_idx", "search", postgresql_using="gin"),
    )


__all__ = ["Chunk", "Source", "SourceKind", "SourceStatus"]
