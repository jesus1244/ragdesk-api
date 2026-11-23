from datetime import datetime
from uuid import UUID

from pydantic import Field

from ragdesk.core.schemas import CustomModel
from ragdesk.sources.models import SourceKind, SourceStatus


class SourceRead(CustomModel):
    id: UUID
    kind: SourceKind
    name: str
    url: str | None
    status: SourceStatus
    error: str | None
    chunk_count: int
    created_at: datetime


class UrlSourceCreate(CustomModel):
    url: str = Field(min_length=8, max_length=2048, examples=["https://example.com/docs"])
    name: str | None = Field(default=None, min_length=1, max_length=255)


class TextSourceCreate(CustomModel):
    name: str = Field(min_length=1, max_length=255)
    text: str = Field(min_length=1, description="Plain text or Markdown")
