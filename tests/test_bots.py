from typing import Any

from httpx import AsyncClient

from tests.conftest import register_and_login


async def _create(
    client: AsyncClient, headers: dict[str, str], name: str = "Docs bot"
) -> dict[str, Any]:
    response = await client.post("/bots", json={"name": name}, headers=headers)
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


async def test_create_bot_returns_public_key_and_defaults(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    bot = await _create(client, auth_headers)
    assert bot["public_key"].startswith("bot_")
    assert bot["allowed_origins"] == []
    assert bot["welcome_message"]


async def test_bots_require_authentication(client: AsyncClient) -> None:
    assert (await client.get("/bots")).status_code == 401
    assert (await client.post("/bots", json={"name": "Docs"})).status_code == 401


async def test_list_is_paginated_and_scoped_to_the_owner(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    for i in range(3):
        await _create(client, auth_headers, f"Bot {i}")
    other = await register_and_login(client, email="bob@example.com")
    await _create(client, other, "Bob bot")

    page = await client.get("/bots", params={"limit": 2}, headers=auth_headers)
    body = page.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2
    assert "Bob bot" not in {b["name"] for b in body["items"]}


async def test_another_users_bot_is_a_404(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    bot = await _create(client, auth_headers)
    other = await register_and_login(client, email="bob@example.com")

    assert (await client.get(f"/bots/{bot['id']}", headers=other)).status_code == 404
    patch = await client.patch(f"/bots/{bot['id']}", json={"name": "Hijacked"}, headers=other)
    assert patch.status_code == 404
    assert (await client.delete(f"/bots/{bot['id']}", headers=other)).status_code == 404
    still_there = await client.get(f"/bots/{bot['id']}", headers=auth_headers)
    assert still_there.json()["name"] == "Docs bot"


async def test_update_changes_only_the_given_fields(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    bot = await _create(client, auth_headers)
    response = await client.patch(
        f"/bots/{bot['id']}", json={"welcome_message": "Hello!"}, headers=auth_headers
    )
    assert response.status_code == 200
    assert response.json()["welcome_message"] == "Hello!"
    assert response.json()["name"] == "Docs bot"


async def test_allowed_origins_are_normalised_and_deduplicated(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    response = await client.post(
        "/bots",
        json={
            "name": "Docs bot",
            "allowed_origins": [
                "https://Example.com/",
                "https://example.com:443",
                "http://localhost:4200/x",
            ],
        },
        headers=auth_headers,
    )
    assert response.status_code == 201
    assert response.json()["allowed_origins"] == ["https://example.com", "http://localhost:4200"]


async def test_invalid_origin_is_rejected(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    response = await client.post(
        "/bots", json={"name": "Docs bot", "allowed_origins": ["not a url"]}, headers=auth_headers
    )
    assert response.status_code == 422


async def test_deleted_bot_disappears(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    bot = await _create(client, auth_headers)
    assert (await client.delete(f"/bots/{bot['id']}", headers=auth_headers)).status_code == 204
    assert (await client.get(f"/bots/{bot['id']}", headers=auth_headers)).status_code == 404
    assert (await client.get("/bots", headers=auth_headers)).json()["total"] == 0
