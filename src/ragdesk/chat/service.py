"""Answer a visitor's question: retrieve passages, stream Claude's answer, store the exchange.

Server-Sent Events sent to the widget, in order:
  meta       {conversation_id}
  delta      {text}                      (many)
  citations  [{index, source_id, source_name, title, snippet}]
  done       {answered}
  error      {message}                   (instead of citations/done when something fails)
"""

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from uuid import UUID

import structlog
from fastapi.sse import ServerSentEvent
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ragdesk.bots.models import Bot
from ragdesk.bots.schemas import normalize_origin
from ragdesk.chat.llm import (
    ChatModelError,
    CitationFound,
    Passage,
    Refused,
    TextDelta,
    Turn,
    get_chat_model,
)
from ragdesk.chat.models import Conversation, Message, MessageRole
from ragdesk.chat.schemas import ChatRequest, CitationRead
from ragdesk.core.config import get_settings
from ragdesk.core.database import SessionFactory
from ragdesk.core.embeddings import EmbeddingError, get_embedder
from ragdesk.core.exceptions import ForbiddenError, NotFoundError
from ragdesk.retrieval.service import Hit, search

log = structlog.get_logger("chat")

NO_ANSWER = "I could not find that in the documentation."
REFUSED = "Sorry, I cannot help with that request."
FAILED = "Sorry, something went wrong. Please try again in a moment."
HISTORY_MESSAGES = 6
SNIPPET_CHARS = 240


@dataclass(frozen=True, slots=True)
class ChatContext:
    bot_id: UUID
    conversation_id: UUID
    question: str
    instructions: str
    history: list[Turn] = field(default_factory=list)


def _event(name: str, data: object) -> ServerSentEvent:
    return ServerSentEvent(raw_data=json.dumps(data, ensure_ascii=False), event=name)


async def get_public_bot(session: AsyncSession, public_key: str, origin: str | None) -> Bot:
    """Find the bot behind a widget key and check that the embedding site is allowed."""
    bot = await session.scalar(
        select(Bot).where(Bot.public_key == public_key, Bot.deleted_at.is_(None))
    )
    if bot is None:
        raise NotFoundError("Assistant not found")
    if bot.allowed_origins and not _origin_allowed(bot.allowed_origins, origin):
        raise ForbiddenError("This website is not allowed to use this assistant")
    return bot


def _origin_allowed(allowed: list[str], origin: str | None) -> bool:
    if origin is None:
        return False
    try:
        return normalize_origin(origin) in allowed
    except ValueError:
        return False


async def open_chat(
    session: AsyncSession, public_key: str, data: ChatRequest, origin: str | None
) -> ChatContext:
    """Validate the request, load or start the conversation and store the visitor's question."""
    bot = await get_public_bot(session, public_key, origin)
    history: list[Turn] = []
    if data.conversation_id is None:
        conversation = Conversation(bot_id=bot.id, visitor_id=data.visitor_id)
        session.add(conversation)
        await session.flush()
    else:
        found = await session.scalar(
            select(Conversation).where(
                Conversation.id == data.conversation_id, Conversation.bot_id == bot.id
            )
        )
        if found is None:
            raise NotFoundError("Conversation not found")
        conversation = found
        history = await _load_history(session, conversation.id)

    session.add(
        Message(
            conversation_id=conversation.id,
            bot_id=bot.id,
            role=MessageRole.USER,
            content=data.question,
        )
    )
    await session.commit()
    return ChatContext(
        bot_id=bot.id,
        conversation_id=conversation.id,
        question=data.question,
        instructions=bot.instructions,
        history=history,
    )


async def _load_history(session: AsyncSession, conversation_id: UUID) -> list[Turn]:
    rows = await session.scalars(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(HISTORY_MESSAGES)
    )
    turns = [
        Turn(role="user" if m.role == MessageRole.USER else "assistant", text=m.content)
        for m in reversed(list(rows))
    ]
    while turns and turns[0].role != "user":  # the API needs a conversation that starts with a user
        turns.pop(0)
    return turns


async def run_chat(ctx: ChatContext) -> AsyncIterator[ServerSentEvent]:
    settings = get_settings()
    yield _event("meta", {"conversation_id": str(ctx.conversation_id)})

    try:
        async with SessionFactory() as session:
            hits = await search(
                session,
                ctx.bot_id,
                ctx.question,
                embedder=get_embedder(),
                top_k=settings.retrieval_top_k,
                candidates=settings.retrieval_candidates,
                max_distance=settings.retrieval_max_distance,
            )
    except EmbeddingError:
        log.exception("chat.retrieval_failed", bot_id=str(ctx.bot_id))
        yield _event("error", {"message": FAILED})
        return

    text_parts: list[str] = []
    citations: dict[UUID, CitationRead] = {}
    refused = False

    if not hits:
        text_parts.append(NO_ANSWER)
        yield _event("delta", {"text": NO_ANSWER})
    else:
        passages = [Passage(str(h.source_id), h.title, h.content) for h in hits]
        try:
            async for event in get_chat_model().stream(
                question=ctx.question,
                history=ctx.history,
                passages=passages,
                instructions=ctx.instructions,
            ):
                if isinstance(event, TextDelta):
                    text_parts.append(event.text)
                    yield _event("delta", {"text": event.text})
                elif isinstance(event, CitationFound):
                    _add_citation(citations, hits, event)
                elif isinstance(event, Refused):
                    refused = True
        except ChatModelError:
            log.exception("chat.model_failed", bot_id=str(ctx.bot_id))
            yield _event("error", {"message": FAILED})
            return

    if refused:
        text_parts = [REFUSED]
        citations.clear()
        yield _event("delta", {"text": REFUSED})

    answer = "".join(text_parts).strip()
    answered = bool(citations)
    await _store_answer(ctx, answer, list(citations.values()), answered=answered)
    yield _event("citations", [c.model_dump(mode="json") for c in citations.values()])
    yield _event("done", {"answered": answered})


def _add_citation(
    citations: dict[UUID, CitationRead], hits: list[Hit], event: CitationFound
) -> None:
    if not 0 <= event.passage_index < len(hits):
        return
    hit = hits[event.passage_index]
    if hit.chunk_id in citations:
        return
    citations[hit.chunk_id] = CitationRead(
        index=len(citations) + 1,
        source_id=hit.source_id,
        source_name=hit.source_name,
        title=hit.title,
        snippet=event.cited_text[:SNIPPET_CHARS],
    )


async def _store_answer(
    ctx: ChatContext, answer: str, citations: list[CitationRead], *, answered: bool
) -> None:
    async with SessionFactory() as session:
        session.add(
            Message(
                conversation_id=ctx.conversation_id,
                bot_id=ctx.bot_id,
                role=MessageRole.ASSISTANT,
                content=answer,
                question=ctx.question,
                answered=answered,
                citations=[c.model_dump(mode="json") for c in citations],
            )
        )
        await session.commit()
