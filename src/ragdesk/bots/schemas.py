from datetime import datetime
from uuid import UUID

from pydantic import AnyHttpUrl, Field, field_validator

from ragdesk.core.schemas import CustomModel

MAX_ORIGINS = 20


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

    @field_validator("allowed_origins")
    @classmethod
    def _normalize_origins(cls, value: list[str]) -> list[str]:
        return normalize_origins(value)


class BotUpdate(CustomModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    welcome_message: str | None = Field(default=None, min_length=1, max_length=300)
    instructions: str | None = Field(default=None, max_length=2000)
    allowed_origins: list[str] | None = Field(default=None, max_length=MAX_ORIGINS)

    @field_validator("allowed_origins")
    @classmethod
    def _normalize_origins(cls, value: list[str] | None) -> list[str] | None:
        return None if value is None else normalize_origins(value)


class BotRead(CustomModel):
    id: UUID
    name: str
    public_key: str
    welcome_message: str
    instructions: str
    allowed_origins: list[str]
    is_demo: bool
    created_at: datetime
