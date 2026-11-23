import secrets
from datetime import datetime
from uuid import UUID

from sqlalchemy import ARRAY, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ragdesk.core.database import Base, TimestampMixin, UUIDPrimaryKeyMixin


def new_public_key() -> str:
    """Unguessable identifier embedded in the public widget snippet (not a secret credential)."""
    return f"bot_{secrets.token_urlsafe(18)}"


class Bot(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A knowledge base plus the settings of the chat widget that answers from it."""

    __tablename__ = "bot"

    owner_id: Mapped[UUID] = mapped_column(
        ForeignKey("auth_user.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    public_key: Mapped[str] = mapped_column(String(64), unique=True, default=new_public_key)
    welcome_message: Mapped[str] = mapped_column(
        String(300), default="Hi! Ask me anything about our documentation."
    )
    instructions: Mapped[str] = mapped_column(Text, default="")
    language: Mapped[str] = mapped_column(String(5), default="en", server_default="en")
    fallback_message: Mapped[str] = mapped_column(String(300), default="", server_default="")
    suggested_questions: Mapped[list[str]] = mapped_column(
        ARRAY(String(120)), default=list, server_default="{}"
    )
    allowed_origins: Mapped[list[str]] = mapped_column(ARRAY(String(255)), default=list)
    is_demo: Mapped[bool] = mapped_column(default=False)
    deleted_at: Mapped[datetime | None]
