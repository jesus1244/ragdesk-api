from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

import ragdesk.models  # noqa: F401  - registers all ORM models
from ragdesk.auth.router import router as auth_router
from ragdesk.bots.router import router as bots_router
from ragdesk.chat.router import router as chat_router
from ragdesk.core.config import get_settings
from ragdesk.core.cors import PublicCorsMiddleware
from ragdesk.core.database import engine
from ragdesk.core.exceptions import register_exception_handlers
from ragdesk.core.logging import RequestContextMiddleware, configure_logging
from ragdesk.core.queue import ArqQueue, get_queue
from ragdesk.core.redis import close_redis, get_redis
from ragdesk.sources.router import router as sources_router


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    yield
    queue = get_queue()
    if isinstance(queue, ArqQueue):
        await queue.close()
    await close_redis()
    await engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description=(
            "Upload documents, then chat with them: hybrid search, answers with citations, "
            "streamed over Server-Sent Events."
        ),
        lifespan=lifespan,
        openapi_url=f"{settings.api_prefix}/openapi.json" if settings.docs_enabled else None,
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url=None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    app.add_middleware(PublicCorsMiddleware, path_prefix=f"{settings.api_prefix}/public/")
    app.add_middleware(RequestContextMiddleware)
    register_exception_handlers(app)

    api = APIRouter(prefix=settings.api_prefix)
    api.include_router(auth_router)
    api.include_router(bots_router)
    api.include_router(sources_router)
    api.include_router(chat_router)
    app.include_router(api)

    @app.get("/health/live", tags=["health"])
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready", tags=["health"])
    async def ready() -> JSONResponse:
        checks: dict[str, Any] = {}
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            checks["database"] = "ok"
        except Exception as exc:
            checks["database"] = f"error: {type(exc).__name__}"
        try:
            await get_redis().ping()
            checks["redis"] = "ok"
        except Exception as exc:
            checks["redis"] = f"error: {type(exc).__name__}"
        healthy = all(v == "ok" for v in checks.values())
        return JSONResponse(
            {"status": "ok" if healthy else "degraded", **checks}, 200 if healthy else 503
        )

    return app


app = create_app()
