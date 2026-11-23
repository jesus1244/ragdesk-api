"""Create (or refresh) the demo owner and a ready-to-chat demo assistant.

    uv run ragdesk-seed-demo

Idempotent. Reads DEMO_EMAIL and DEMO_PASSWORD from the environment; when the password is not set a
random one is generated and printed once, only when the account is created.
"""

import asyncio
import os
import secrets
import string
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ragdesk.auth.models import User
from ragdesk.auth.schemas import RegisterRequest
from ragdesk.auth.service import register_user
from ragdesk.bots.models import Bot
from ragdesk.bots.schemas import BotCreate, BotUpdate
from ragdesk.bots.service import create_bot, update_bot
from ragdesk.core.database import SessionFactory, engine
from ragdesk.core.embeddings import Embedder, get_embedder
from ragdesk.demo.content import DEMO_ASSISTANTS, DemoAssistant
from ragdesk.ingestion.service import ingest_source
from ragdesk.sources.models import Source, SourceKind


def _random_password() -> str:
    alphabet = string.ascii_letters + string.digits
    return "Aa1" + "".join(secrets.choice(alphabet) for _ in range(16))


async def _ensure_assistant(
    session: AsyncSession, owner_id: UUID, demo: DemoAssistant, embedder: Embedder
) -> Bot:
    settings = {
        "welcome_message": demo.welcome,
        "language": demo.language,
        "fallback_message": demo.fallback,
        "suggested_questions": demo.suggested_questions,
    }
    bot = await session.scalar(
        select(Bot).where(Bot.owner_id == owner_id, Bot.is_demo.is_(True), Bot.name == demo.name)
    )
    if bot is None:
        bot = await create_bot(session, owner_id, BotCreate(name=demo.name, **settings))
        bot.is_demo = True
        await session.commit()
    else:
        bot = await update_bot(session, bot, BotUpdate(**settings))

    existing = set(await session.scalars(select(Source.name).where(Source.bot_id == bot.id)))
    for name, text in demo.documents.items():
        if name in existing:
            continue
        source = Source(
            bot_id=bot.id,
            kind=SourceKind.FILE,
            name=name,
            content_type="text/markdown",
            raw=text.encode(),
        )
        session.add(source)
        await session.commit()
        await ingest_source(session, source.id, embedder=embedder)
    return bot


async def seed_demo(
    session: AsyncSession, *, embedder: Embedder, email: str, password: str
) -> tuple[list[Bot], bool]:
    """Returns the demo assistants (English, Spanish) and whether the owner was created now."""
    created = False
    user = await session.scalar(select(User).where(User.email == email))
    if user is None:
        user = await register_user(
            session, RegisterRequest(email=email, full_name="Demo Owner", password=password)
        )
        created = True
    bots = [await _ensure_assistant(session, user.id, d, embedder) for d in DEMO_ASSISTANTS]
    return bots, created


async def _run() -> None:
    email = os.environ.get("DEMO_EMAIL", "demo@ragdesk.dev").lower()
    password = os.environ.get("DEMO_PASSWORD") or _random_password()
    try:
        async with SessionFactory() as session:
            bots, created = await seed_demo(
                session, embedder=get_embedder(), email=email, password=password
            )
            for bot in bots:
                print(f"Demo assistant ready: {bot.name} ({bot.language})")
                print(f"  Widget key: {bot.public_key}")
            if created:
                print(f"Demo owner created: {email} / {password}  (shown once)")
            else:
                print(f"Demo owner already existed: {email}")
    finally:
        await engine.dispose()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
