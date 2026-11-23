from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ragdesk.core.database import Base, UUIDPrimaryKeyMixin, utcnow


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class Conversation(UUIDPrimaryKeyMixin, Base):
    """One visitor session with a bot's widget."""

    __tablename__ = "conversation"

    bot_id: Mapped[UUID] = mapped_column(ForeignKey("bot.id", ondelete="CASCADE"), index=True)
    visitor_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Message(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "message"

    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversation.id", ondelete="CASCADE"), index=True
    )
    bot_id: Mapped[UUID] = mapped_column(ForeignKey("bot.id", ondelete="CASCADE"))
    role: Mapped[MessageRole] = mapped_column(String(10))
    content: Mapped[str] = mapped_column(Text)
    # Assistant messages only. `question` repeats the visitor's question so the owner can list
    # unanswered questions without a join; `answered` is true when the answer cites a passage.
    question: Mapped[str | None] = mapped_column(Text)
    answered: Mapped[bool | None]
    citations: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    __table_args__ = (Index("message_bot_id_created_at_idx", "bot_id", "created_at"),)
