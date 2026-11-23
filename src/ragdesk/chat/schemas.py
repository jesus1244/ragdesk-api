from datetime import datetime
from uuid import UUID

from pydantic import Field

from ragdesk.chat.models import MessageRole
from ragdesk.core.schemas import CustomModel

MAX_QUESTION_CHARS = 1000


class ChatRequest(CustomModel):
    question: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)
    conversation_id: UUID | None = Field(
        default=None,
        description="Omit on the first question; send the id from the `meta` event after.",
    )
    visitor_id: str | None = Field(
        default=None,
        max_length=64,
        description="Random id the widget keeps in the visitor's browser.",
    )


class CitationRead(CustomModel):
    index: int = Field(description="1-based number shown next to the answer, e.g. [1]")
    source_id: UUID
    source_name: str
    title: str
    snippet: str


class WidgetConfig(CustomModel):
    name: str
    welcome_message: str
    language: str
    suggested_questions: list[str]


class MessageRead(CustomModel):
    id: UUID
    role: MessageRole
    content: str
    citations: list[CitationRead]
    answered: bool | None
    created_at: datetime


class ConversationRead(CustomModel):
    id: UUID
    visitor_id: str | None
    created_at: datetime
    message_count: int
    last_question: str | None


class UnansweredRead(CustomModel):
    message_id: UUID
    conversation_id: UUID
    question: str
    created_at: datetime
