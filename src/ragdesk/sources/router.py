from pathlib import PurePath
from typing import Annotated, Any
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, UploadFile, status

from ragdesk.auth.dependencies import CurrentUser, SessionDep
from ragdesk.bots.service import get_owned_bot
from ragdesk.core.config import get_settings
from ragdesk.core.exceptions import UnprocessableError
from ragdesk.core.rate_limit import rate_limit
from ragdesk.core.schemas import ErrorResponse, Page
from ragdesk.ingestion.errors import IngestionError
from ragdesk.ingestion.extract import PLAIN, content_type_for
from ragdesk.ingestion.fetch import validate_url
from ragdesk.sources import service
from ragdesk.sources.models import SourceKind
from ragdesk.sources.schemas import SourceRead, TextSourceCreate, UrlSourceCreate

router = APIRouter(prefix="/bots/{bot_id}/sources", tags=["sources"])

NOT_FOUND: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "Bot or source not found"}
}
_upload_limit = Depends(rate_limit("upload", get_settings().rate_limit_upload_per_minute))


@router.get("", response_model=Page[SourceRead], responses=NOT_FOUND)
async def list_sources(
    bot_id: UUID,
    user: CurrentUser,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[SourceRead]:
    await get_owned_bot(session, user.id, bot_id)
    sources, total = await service.list_sources(session, bot_id, limit=limit, offset=offset)
    return Page(
        items=[SourceRead.model_validate(s) for s in sources],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/file",
    response_model=SourceRead,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[_upload_limit],
    responses=NOT_FOUND,
)
async def upload_file(
    bot_id: UUID, user: CurrentUser, session: SessionDep, file: Annotated[UploadFile, File()]
) -> SourceRead:
    """Upload a PDF, Markdown, text or HTML file. Processing happens in the background."""
    await get_owned_bot(session, user.id, bot_id)
    filename = PurePath(file.filename or "").name
    content_type = content_type_for(filename)
    if not filename or content_type is None:
        raise UnprocessableError("Supported files: .pdf, .md, .markdown, .txt, .html")
    limit = get_settings().max_upload_bytes
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise UnprocessableError(f"Files are limited to {get_settings().max_upload_mb} MB")
    if not data:
        raise UnprocessableError("The file is empty")
    source = await service.create_source(
        session,
        bot_id,
        kind=SourceKind.FILE,
        name=filename[:255],
        content_type=content_type,
        raw=data,
    )
    return SourceRead.model_validate(source)


@router.post(
    "/url",
    response_model=SourceRead,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[_upload_limit],
    responses=NOT_FOUND,
)
async def add_url(
    bot_id: UUID, data: UrlSourceCreate, user: CurrentUser, session: SessionDep
) -> SourceRead:
    """Add a web page. The address is checked now and again when it is downloaded."""
    await get_owned_bot(session, user.id, bot_id)
    try:
        url = await validate_url(data.url)
    except IngestionError as exc:
        raise UnprocessableError(str(exc)) from exc
    name = data.name or urlsplit(url).netloc
    source = await service.create_source(
        session, bot_id, kind=SourceKind.URL, name=name[:255], url=url
    )
    return SourceRead.model_validate(source)


@router.post(
    "/text",
    response_model=SourceRead,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[_upload_limit],
    responses=NOT_FOUND,
)
async def add_text(
    bot_id: UUID, data: TextSourceCreate, user: CurrentUser, session: SessionDep
) -> SourceRead:
    """Add pasted text or Markdown, for example an FAQ."""
    await get_owned_bot(session, user.id, bot_id)
    if len(data.text) > get_settings().max_text_chars:
        raise UnprocessableError("The text is too long")
    source = await service.create_source(
        session,
        bot_id,
        kind=SourceKind.TEXT,
        name=data.name,
        content_type=PLAIN,
        raw=data.text.encode(),
    )
    return SourceRead.model_validate(source)


@router.get("/{source_id}", response_model=SourceRead, responses=NOT_FOUND)
async def get_source(
    bot_id: UUID, source_id: UUID, user: CurrentUser, session: SessionDep
) -> SourceRead:
    await get_owned_bot(session, user.id, bot_id)
    return SourceRead.model_validate(await service.get_source(session, bot_id, source_id))


@router.post(
    "/{source_id}/retry",
    response_model=SourceRead,
    status_code=status.HTTP_202_ACCEPTED,
    responses=NOT_FOUND,
)
async def retry_source(
    bot_id: UUID, source_id: UUID, user: CurrentUser, session: SessionDep
) -> SourceRead:
    await get_owned_bot(session, user.id, bot_id)
    source = await service.get_source(session, bot_id, source_id)
    return SourceRead.model_validate(await service.retry_source(session, source))


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT, responses=NOT_FOUND)
async def delete_source(
    bot_id: UUID, source_id: UUID, user: CurrentUser, session: SessionDep
) -> None:
    await get_owned_bot(session, user.id, bot_id)
    await service.delete_source(session, await service.get_source(session, bot_id, source_id))
