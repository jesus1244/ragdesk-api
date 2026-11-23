from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import AnyHttpUrl, Field, field_validator

from ragdesk.core.schemas import CustomModel

MAX_ORIGINS = 20
MAX_SUGGESTED_QUESTIONS = 4
MAX_SUGGESTED_LENGTH = 120

Language = Literal["en", "es"]


def normalize_origin(origin: str) -> str:
    """Reduce an origin to scheme://host[:port] so it can be compared exactly."""
    parsed = AnyHttpUrl(origin)
    host = parsed.host or ""
    default_port = 443 if parsed.scheme == "https" else 80
    port = f":{parsed.port}" if parsed.port and parsed.port != default_port else ""
    return f"{parsed.scheme}://{host}{port}"


def normalize_origins(origins: list[str]) -> list[str]:
    try:
        normalized = [normalize_origin(o) for o in origins]
    except ValueError as exc:
        raise ValueError("Each origin must be a valid http(s) URL") from exc
    return list(dict.fromkeys(normalized))


def normalize_questions(questions: list[str]) -> list[str]:
    """Trim, drop blanks and duplicates, keep the owner's order."""
    cleaned = [q.strip() for q in questions if q.strip()]
    if any(len(q) > MAX_SUGGESTED_LENGTH for q in cleaned):
        raise ValueError(
            f"Each suggested question must be at most {MAX_SUGGESTED_LENGTH} characters"
        )
    unique = list(dict.fromkeys(cleaned))
    if len(unique) > MAX_SUGGESTED_QUESTIONS:
        raise ValueError(f"At most {MAX_SUGGESTED_QUESTIONS} suggested questions")
    return unique


class BotCreate(CustomModel):
    name: str = Field(min_length=2, max_length=120)
    welcome_message: str = Field(
        default="Hi! Ask me anything about our documentation.", min_length=1, max_length=300
    )
    instructions: str = Field(
        default="",
        max_length=2000,
        description="Extra guidance for the assistant, e.g. tone or topics to avoid.",
    )
    allowed_origins: list[str] = Field(
        default_factory=list,
        max_length=MAX_ORIGINS,
        description="Websites allowed to embed the widget, e.g. https://example.com",
    )
    language: Language = Field(
        default="en", description="Language of the widget texts and default messages."
    )
    fallback_message: str = Field(
        default="",
        max_length=300,
        description="Shown when nothing in the documents matches. Empty uses a default.",
    )
    suggested_questions: list[str] = Field(
        default_factory=list,
        description="Up to four questions shown as buttons when the chat opens.",
    )

    @field_validator("allowed_origins")
    @classmethod
    def _normalize_origins(cls, value: list[str]) -> list[str]:
        return normalize_origins(value)

    @field_validator("suggested_questions")
    @classmethod
    def _normalize_questions(cls, value: list[str]) -> list[str]:
        return normalize_questions(value)


class BotUpdate(CustomModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    welcome_message: str | None = Field(default=None, min_length=1, max_length=300)
    instructions: str | None = Field(default=None, max_length=2000)
    allowed_origins: list[str] | None = Field(default=None, max_length=MAX_ORIGINS)
    language: Language | None = None
    fallback_message: str | None = Field(default=None, max_length=300)
    suggested_questions: list[str] | None = None

    @field_validator("allowed_origins")
    @classmethod
    def _normalize_origins(cls, value: list[str] | None) -> list[str] | None:
        return None if value is None else normalize_origins(value)

    @field_validator("suggested_questions")
    @classmethod
    def _normalize_questions(cls, value: list[str] | None) -> list[str] | None:
        return None if value is None else normalize_questions(value)


class BotRead(CustomModel):
    id: UUID
    name: str
    public_key: str
    welcome_message: str
    instructions: str
    allowed_origins: list[str]
    language: Language
    fallback_message: str
    suggested_questions: list[str]
    is_demo: bool
    created_at: datetime
