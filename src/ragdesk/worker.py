"""ARQ worker entrypoint: `arq ragdesk.worker.WorkerSettings`."""

from typing import Any, ClassVar

from arq import func

import ragdesk.models  # noqa: F401  - registers all ORM models
from ragdesk.core.logging import configure_logging
from ragdesk.core.queue import redis_settings
from ragdesk.ingestion.tasks import MAX_TRIES, ingest_source_job


async def startup(ctx: dict[str, Any]) -> None:
    configure_logging()


class WorkerSettings:
    functions: ClassVar = [func(ingest_source_job, name="ingest_source", max_tries=MAX_TRIES)]
    redis_settings = redis_settings()
    on_startup = startup
    job_timeout = 300
    keep_result = 60
