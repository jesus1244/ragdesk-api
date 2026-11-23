"""Background job queue (ARQ on Redis), behind a small interface so tests can swap it.

Jobs that must not run twice for the same entity pass a deterministic `job_id`: ARQ ignores a second
enqueue while a job with that id is still queued or running.
"""

from typing import Any, Protocol

from arq import ArqRedis, create_pool
from arq.connections import RedisSettings

from ragdesk.core.config import get_settings


class JobQueue(Protocol):
    async def enqueue(self, function: str, *args: Any, job_id: str | None = None) -> None: ...


def redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(get_settings().redis_url)


class ArqQueue:
    def __init__(self) -> None:
        self._pool: ArqRedis | None = None

    async def enqueue(self, function: str, *args: Any, job_id: str | None = None) -> None:
        if self._pool is None:
            self._pool = await create_pool(redis_settings())
        await self._pool.enqueue_job(function, *args, _job_id=job_id)

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.aclose()
            self._pool = None


_queue: JobQueue = ArqQueue()


def get_queue() -> JobQueue:
    return _queue


def set_queue(queue: JobQueue) -> None:
    global _queue  # noqa: PLW0603
    _queue = queue
