"""Public endpoints used by the embeddable widget. They need no login: the bot's public key plus the
allowed-origins list identify the assistant, and every call is rate limited."""

from collections.abc import AsyncIterable
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.sse import EventSourceResponse, ServerSentEvent

from ragdesk.auth.dependencies import SessionDep
from ragdesk.chat import service
from ragdesk.chat.schemas import ChatRequest, WidgetConfig
from ragdesk.core.config import get_settings
from ragdesk.core.rate_limit import rate_limit
from ragdesk.core.schemas import ErrorResponse

router = APIRouter(prefix="/public", tags=["public"])

ERRORS: dict[int | str, dict[str, Any]] = {
    403: {"model": ErrorResponse, "description": "Website not allowed"},
    404: {"model": ErrorResponse, "description": "Assistant or conversation not found"},
}


async def chat_context(
    public_key: str, data: ChatRequest, request: Request, session: SessionDep
) -> service.ChatContext:
    """Runs before streaming starts, so 403/404 are real HTTP errors rather than stream events."""
    return await service.open_chat(session, public_key, data, request.headers.get("origin"))


@router.get("/bots/{public_key}", response_model=WidgetConfig, responses=ERRORS)
async def widget_config(public_key: str, request: Request, session: SessionDep) -> WidgetConfig:
    bot = await service.get_public_bot(session, public_key, request.headers.get("origin"))
    return WidgetConfig(name=bot.name, welcome_message=bot.welcome_message)


@router.post(
    "/chat/{public_key}",
    response_class=EventSourceResponse,
    dependencies=[Depends(rate_limit("chat", get_settings().rate_limit_chat_per_minute))],
    responses=ERRORS,
)
async def chat(
    ctx: Annotated[service.ChatContext, Depends(chat_context)],
) -> AsyncIterable[ServerSentEvent]:
    """Ask a question. The answer streams as Server-Sent Events: meta, delta*, citations, done."""
    async for event in service.run_chat(ctx):
        yield event
