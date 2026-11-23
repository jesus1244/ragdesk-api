import httpx
import pytest
import respx

from ragdesk.core.config import get_settings
from ragdesk.ingestion import fetch
from ragdesk.ingestion.errors import IngestionError


@pytest.fixture(autouse=True)
def dns(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[str]]:
    """Fake DNS: tests decide what each host resolves to."""
    table: dict[str, list[str]] = {"docs.example.com": ["93.184.216.34"]}

    async def resolve(host: str, port: int) -> list[str]:
        if host not in table:
            raise IngestionError("The address could not be resolved")
        return table[host]

    monkeypatch.setattr(fetch, "_resolve", resolve)
    return table


@pytest.mark.parametrize(
    ("url", "message"),
    [
        ("ftp://docs.example.com/a", "Only http"),
        ("file:///etc/passwd", "Only http"),
        ("http://user:pw@docs.example.com/", "credentials"),
        ("http://docs.example.com:8080/", "ports 80 and 443"),
        ("http:///nohost", "Only http"),
    ],
)
async def test_unsafe_urls_are_rejected(url: str, message: str) -> None:
    with pytest.raises(IngestionError, match=message):
        await fetch.validate_url(url)


@pytest.mark.parametrize(
    "address",
    ["127.0.0.1", "10.0.0.5", "192.168.1.10", "172.16.0.1", "169.254.169.254", "::1", "fd00::1"],
)
async def test_hosts_resolving_to_private_addresses_are_rejected(
    address: str, dns: dict[str, list[str]]
) -> None:
    dns["evil.example.com"] = [address]
    with pytest.raises(IngestionError, match="not publicly reachable"):
        await fetch.validate_url("https://evil.example.com/")


async def test_one_private_address_among_public_ones_is_enough_to_reject(
    dns: dict[str, list[str]],
) -> None:
    dns["mixed.example.com"] = ["93.184.216.34", "10.0.0.1"]
    with pytest.raises(IngestionError, match="not publicly reachable"):
        await fetch.validate_url("https://mixed.example.com/")


@respx.mock
async def test_html_page_is_downloaded() -> None:
    respx.get("https://docs.example.com/guide").respond(
        200, text="<html>hi</html>", headers={"content-type": "text/html; charset=utf-8"}
    )
    page = await fetch.fetch_url("https://docs.example.com/guide")
    assert page.content_type == "text/html"
    assert page.body == b"<html>hi</html>"


@respx.mock
async def test_redirect_to_a_private_host_is_blocked(dns: dict[str, list[str]]) -> None:
    dns["internal.example.com"] = ["10.0.0.7"]
    respx.get("https://docs.example.com/go").respond(
        302, headers={"location": "https://internal.example.com/admin"}
    )
    with pytest.raises(IngestionError, match="not publicly reachable"):
        await fetch.fetch_url("https://docs.example.com/go")


@respx.mock
async def test_redirect_to_a_public_host_is_followed() -> None:
    respx.get("https://docs.example.com/old").respond(301, headers={"location": "/new"})
    respx.get("https://docs.example.com/new").respond(
        200, text="moved", headers={"content-type": "text/plain"}
    )
    page = await fetch.fetch_url("https://docs.example.com/old")
    assert page.body == b"moved"
    assert page.url == "https://docs.example.com/new"


@respx.mock
async def test_redirect_loops_stop() -> None:
    respx.get("https://docs.example.com/loop").respond(302, headers={"location": "/loop"})
    with pytest.raises(IngestionError, match="Too many redirects"):
        await fetch.fetch_url("https://docs.example.com/loop")


@respx.mock
async def test_non_text_content_is_rejected() -> None:
    respx.get("https://docs.example.com/file").respond(
        200, content=b"\x89PNG", headers={"content-type": "image/png"}
    )
    with pytest.raises(IngestionError, match="HTML or plain text"):
        await fetch.fetch_url("https://docs.example.com/file")


@respx.mock
async def test_error_status_is_reported_without_the_body() -> None:
    respx.get("https://docs.example.com/missing").respond(404, text="secret internal detail")
    with pytest.raises(IngestionError, match="status 404") as info:
        await fetch.fetch_url("https://docs.example.com/missing")
    assert "secret" not in str(info.value)


@respx.mock
async def test_oversized_pages_are_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("URL_FETCH_MAX_MB", "1")
    get_settings.cache_clear()
    try:
        respx.get("https://docs.example.com/big").respond(
            200, content=b"x" * (2 * 1024 * 1024), headers={"content-type": "text/plain"}
        )
        with pytest.raises(IngestionError, match="too large"):
            await fetch.fetch_url("https://docs.example.com/big")
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


@respx.mock
async def test_network_failures_become_safe_errors() -> None:
    respx.get("https://docs.example.com/down").mock(side_effect=httpx.ConnectError("refused"))
    with pytest.raises(IngestionError, match="could not be downloaded"):
        await fetch.fetch_url("https://docs.example.com/down")


@respx.mock
async def test_timeouts_become_safe_errors() -> None:
    respx.get("https://docs.example.com/slow").mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(IngestionError, match="too long"):
        await fetch.fetch_url("https://docs.example.com/slow")
