"""Test setup.

- Postgres (with pgvector) is real: testcontainers locally, TEST_DATABASE_URL in CI. The schema is
  built by running the Alembic migrations, so migrations are tested too.
- Redis is replaced by fakeredis; the job queue runs jobs inline so flows are end to end.
- ragdesk is imported lazily: settings and the engine must see the env vars set here first.
"""

import os
from collections.abc import AsyncIterator, Iterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

_container: Any = None
PGVECTOR_IMAGE = "pgvector/pgvector:pg18-trixie"


def pytest_configure(config: pytest.Config) -> None:
    global _container  # noqa: PLW0603
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        from testcontainers.community.postgres import PostgresContainer

        _container = PostgresContainer(PGVECTOR_IMAGE, driver="asyncpg").start()
        url = _container.get_connection_url()
    os.environ.update(
        {
            "DATABASE_URL": url,
            "ENVIRONMENT": "test",
            "EMBEDDER": "fake",
            "CHAT_MODEL_PROVIDER": "fake",
            "RATE_LIMIT_AUTH_PER_MINUTE": "1000",
            "RATE_LIMIT_UPLOAD_PER_MINUTE": "1000",
            "RATE_LIMIT_CHAT_PER_MINUTE": "1000",
            "URL_ALLOW_PRIVATE_HOSTS": "false",
            "JWT_SECRET": "test-secret-that-is-long-enough-for-hs256-signing",
        }
    )


def pytest_unconfigure(config: pytest.Config) -> None:
    if _container is not None:
        _container.stop()


class InlineQueue:
    """Runs jobs immediately, in-process, and records every call for assertions."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...], str | None]] = []
        self.retries: list[str] = []

    async def enqueue(self, function: str, *args: Any, job_id: str | None = None) -> None:
        from arq import Retry

        from ragdesk.ingestion.tasks import ingest_source_job

        self.calls.append((function, args, job_id))
        jobs = {"ingest_source": ingest_source_job}
        try:
            await jobs[function]({"job_try": 1}, *args)
        except Retry:
            self.retries.append(function)


@pytest.fixture(scope="session", autouse=True)
def _migrate_database() -> Iterator[None]:
    from alembic import command
    from alembic.config import Config

    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")
    yield
    command.downgrade(cfg, "base")


@pytest.fixture(autouse=True)
async def _clean_state() -> AsyncIterator[None]:
    import fakeredis
    from sqlalchemy import text

    from ragdesk.core import embeddings, queue, redis
    from ragdesk.core.database import engine

    redis.set_redis(fakeredis.FakeAsyncRedis(decode_responses=True))
    queue.set_queue(InlineQueue())
    embeddings.set_embedder(embeddings.FakeEmbedder())
    yield
    tables = "auth_user, auth_refresh_token, bot, source, chunk, conversation, message"
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} CASCADE"))


@pytest.fixture
def inline_queue() -> InlineQueue:
    from ragdesk.core.queue import get_queue

    q = get_queue()
    assert isinstance(q, InlineQueue)
    return q


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    from ragdesk.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test/api/v1") as ac:
        yield ac


async def register_and_login(
    client: AsyncClient, email: str = "ana@example.com", password: str = "Secret123"
) -> dict[str, str]:
    await client.post(
        "/auth/register", json={"email": email, "full_name": "Ana Test", "password": password}
    )
    response = await client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
async def auth_headers(client: AsyncClient) -> dict[str, str]:
    return await register_and_login(client)
