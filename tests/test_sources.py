from typing import Any
from uuid import UUID

import pytest
import respx
from httpx import AsyncClient
from sqlalchemy import func, select

from ragdesk.core.config import get_settings
from ragdesk.core.database import SessionFactory
from ragdesk.ingestion import fetch
from ragdesk.sources.models import Chunk
from tests.conftest import InlineQueue, register_and_login
from tests.pdfs import make_pdf

GUIDE = b"# Guide\n\n## Refunds\n\nRefunds are issued within 14 days.\n\n## Shipping\n\nShipping takes 3 days.\n"


async def _bot(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post("/bots", json={"name": "Docs bot"}, headers=headers)
    return str(response.json()["id"])


async def _upload(
    client: AsyncClient,
    headers: dict[str, str],
    bot_id: str,
    name: str = "guide.md",
    data: bytes = GUIDE,
) -> Any:
    return await client.post(
        f"/bots/{bot_id}/sources/file", files={"file": (name, data)}, headers=headers
    )


async def _chunk_count(source_id: str) -> int:
    async with SessionFactory() as session:
        return (
            await session.scalar(
                select(func.count()).select_from(Chunk).where(Chunk.source_id == UUID(source_id))
            )
            or 0
        )


async def test_uploaded_markdown_is_ingested_into_chunks(
    client: AsyncClient, auth_headers: dict[str, str], inline_queue: InlineQueue
) -> None:
    bot_id = await _bot(client, auth_headers)
    response = await _upload(client, auth_headers, bot_id)
    assert response.status_code == 202
    source = response.json()

    assert inline_queue.calls == [("ingest_source", (source["id"],), f"ingest:{source['id']}")]
    done = (await client.get(f"/bots/{bot_id}/sources/{source['id']}", headers=auth_headers)).json()
    assert done["status"] == "ready"
    assert done["chunk_count"] == 2
    assert await _chunk_count(source["id"]) == 2


async def test_pdf_upload_is_ingested_per_page(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    bot_id = await _bot(client, auth_headers)
    pdf = make_pdf([["Page one text."], ["Page two text."]])
    source = (await _upload(client, auth_headers, bot_id, "policy.pdf", pdf)).json()
    done = (await client.get(f"/bots/{bot_id}/sources/{source['id']}", headers=auth_headers)).json()
    assert done["status"] == "ready"
    assert done["chunk_count"] == 2


async def test_text_source_is_ingested(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    bot_id = await _bot(client, auth_headers)
    response = await client.post(
        f"/bots/{bot_id}/sources/text",
        json={"name": "FAQ", "text": "# FAQ\n\nWe open at 9am."},
        headers=auth_headers,
    )
    assert response.status_code == 202
    done = (
        await client.get(f"/bots/{bot_id}/sources/{response.json()['id']}", headers=auth_headers)
    ).json()
    assert done["status"] == "ready"
    assert done["kind"] == "text"


async def test_unreadable_file_is_marked_failed_with_a_safe_message(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    bot_id = await _bot(client, auth_headers)
    source = (await _upload(client, auth_headers, bot_id, "broken.pdf", b"%PDF-1.4 nope")).json()
    done = (await client.get(f"/bots/{bot_id}/sources/{source['id']}", headers=auth_headers)).json()
    assert done["status"] == "failed"
    assert done["error"] == "The PDF could not be read"
    assert await _chunk_count(source["id"]) == 0


async def test_unsupported_and_empty_files_are_rejected(
    client: AsyncClient, auth_headers: dict[str, str], inline_queue: InlineQueue
) -> None:
    bot_id = await _bot(client, auth_headers)
    assert (await _upload(client, auth_headers, bot_id, "tool.exe", b"MZ")).status_code == 422
    assert (await _upload(client, auth_headers, bot_id, "empty.txt", b"")).status_code == 422
    assert inline_queue.calls == []


async def test_oversized_uploads_are_rejected(
    client: AsyncClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MAX_UPLOAD_MB", "1")
    get_settings.cache_clear()
    try:
        bot_id = await _bot(client, auth_headers)
        response = await _upload(client, auth_headers, bot_id, "big.txt", b"x" * (1024 * 1024 + 1))
        assert response.status_code == 422
        assert "limited" in response.json()["message"]
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


async def test_source_limit_per_bot(
    client: AsyncClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MAX_SOURCES_PER_BOT", "2")
    get_settings.cache_clear()
    try:
        bot_id = await _bot(client, auth_headers)
        assert (await _upload(client, auth_headers, bot_id, "a.md")).status_code == 202
        assert (await _upload(client, auth_headers, bot_id, "b.md")).status_code == 202
        assert (await _upload(client, auth_headers, bot_id, "c.md")).status_code == 409
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


async def test_another_users_bot_sources_are_a_404(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    bot_id = await _bot(client, auth_headers)
    source = (await _upload(client, auth_headers, bot_id)).json()
    other = await register_and_login(client, email="bob@example.com")

    assert (await client.get(f"/bots/{bot_id}/sources", headers=other)).status_code == 404
    assert (await _upload(client, other, bot_id)).status_code == 404
    assert (
        await client.get(f"/bots/{bot_id}/sources/{source['id']}", headers=other)
    ).status_code == 404
    assert (
        await client.delete(f"/bots/{bot_id}/sources/{source['id']}", headers=other)
    ).status_code == 404
    assert await _chunk_count(source["id"]) == 2


async def test_a_source_cannot_be_read_through_another_bot(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    first = await _bot(client, auth_headers)
    second = await _bot(client, auth_headers)
    source = (await _upload(client, auth_headers, first)).json()
    response = await client.get(f"/bots/{second}/sources/{source['id']}", headers=auth_headers)
    assert response.status_code == 404


async def test_deleting_a_source_removes_its_chunks(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    bot_id = await _bot(client, auth_headers)
    source = (await _upload(client, auth_headers, bot_id)).json()
    assert await _chunk_count(source["id"]) == 2
    response = await client.delete(f"/bots/{bot_id}/sources/{source['id']}", headers=auth_headers)
    assert response.status_code == 204
    assert await _chunk_count(source["id"]) == 0
    assert (await client.get(f"/bots/{bot_id}/sources", headers=auth_headers)).json()["total"] == 0


async def test_list_is_paginated(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    bot_id = await _bot(client, auth_headers)
    for i in range(3):
        await _upload(client, auth_headers, bot_id, f"doc{i}.md")
    page = (
        await client.get(f"/bots/{bot_id}/sources", params={"limit": 2}, headers=auth_headers)
    ).json()
    assert page["total"] == 3
    assert len(page["items"]) == 2


async def test_running_the_job_twice_does_not_duplicate_chunks(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    from ragdesk.core.embeddings import get_embedder
    from ragdesk.ingestion.service import ingest_source

    bot_id = await _bot(client, auth_headers)
    source = (await _upload(client, auth_headers, bot_id)).json()
    async with SessionFactory() as session:
        again = await ingest_source(session, UUID(source["id"]), embedder=get_embedder())
    assert again is True
    assert await _chunk_count(source["id"]) == 2


async def test_failed_source_can_be_retried_but_a_ready_one_cannot(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    bot_id = await _bot(client, auth_headers)
    ready = (await _upload(client, auth_headers, bot_id)).json()
    response = await client.post(
        f"/bots/{bot_id}/sources/{ready['id']}/retry", headers=auth_headers
    )
    assert response.status_code == 409

    failed = (await _upload(client, auth_headers, bot_id, "bad.pdf", b"%PDF-1.4 nope")).json()
    retry = await client.post(f"/bots/{bot_id}/sources/{failed['id']}/retry", headers=auth_headers)
    assert retry.status_code == 202


@pytest.fixture
def public_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    async def resolve(host: str, port: int) -> list[str]:
        return ["93.184.216.34"]

    monkeypatch.setattr(fetch, "_resolve", resolve)


@respx.mock
@pytest.mark.usefixtures("public_dns")
async def test_url_source_is_downloaded_and_ingested(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    sentence = "Orders can be returned within thirty days for a full refund. "
    respx.get("https://docs.example.com/returns").respond(
        200,
        text=(
            "<html><head><title>Returns</title></head><body><article><h1>Returns</h1>"
            f"<p>{sentence * 8}</p></article></body></html>"
        ),
        headers={"content-type": "text/html"},
    )
    bot_id = await _bot(client, auth_headers)
    response = await client.post(
        f"/bots/{bot_id}/sources/url",
        json={"url": "https://docs.example.com/returns"},
        headers=auth_headers,
    )
    assert response.status_code == 202
    assert response.json()["name"] == "docs.example.com"
    done = (
        await client.get(f"/bots/{bot_id}/sources/{response.json()['id']}", headers=auth_headers)
    ).json()
    assert done["status"] == "ready"
    assert done["chunk_count"] >= 1


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/admin",
        "http://127.0.0.1:8000/",
        "http://169.254.169.254/latest/meta-data/",
        "file:///etc/passwd",
        "ftp://example.com/x",
    ],
)
async def test_internal_urls_are_rejected_before_anything_is_stored(
    client: AsyncClient, auth_headers: dict[str, str], inline_queue: InlineQueue, url: str
) -> None:
    bot_id = await _bot(client, auth_headers)
    response = await client.post(
        f"/bots/{bot_id}/sources/url", json={"url": url}, headers=auth_headers
    )
    assert response.status_code == 422
    assert inline_queue.calls == []
    assert (await client.get(f"/bots/{bot_id}/sources", headers=auth_headers)).json()["total"] == 0
