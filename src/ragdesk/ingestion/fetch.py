"""Fetch a user-supplied URL without letting it reach internal services (SSRF guard).

Every hop is checked: the scheme and port must be web-safe, and every address the host resolves to
must be a public one. Redirects are followed manually (at most `MAX_REDIRECTS`) so each target is
re-checked. Size and time are capped, and only HTML or plain text is accepted.

Known limit: a hostile DNS server could answer differently between this check and the connection
(DNS rebinding). Production deployments should also block private ranges on the egress firewall.
"""

import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import httpx

from ragdesk.core.config import get_settings
from ragdesk.ingestion.errors import IngestionError

MAX_REDIRECTS = 3
ALLOWED_PORTS = {80, 443}
ACCEPTED_TYPES = ("text/html", "text/plain", "application/xhtml+xml")
USER_AGENT = "RAGDeskBot/0.1 (+document ingestion)"


@dataclass(frozen=True, slots=True)
class FetchedPage:
    url: str
    content_type: str
    body: bytes


async def _resolve(host: str, port: int) -> list[str]:
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise IngestionError("The address could not be resolved") from exc
    return [str(info[4][0]) for info in infos]


async def validate_url(url: str) -> str:
    """Return the URL if it is safe to fetch, otherwise raise IngestionError."""
    settings = get_settings()
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise IngestionError("Only http(s) URLs are supported")
    if parts.username or parts.password:
        raise IngestionError("URLs with credentials are not allowed")
    try:
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError as exc:
        raise IngestionError("The URL has an invalid port") from exc
    if not settings.url_allow_private_hosts:
        if port not in ALLOWED_PORTS:
            raise IngestionError("Only ports 80 and 443 are allowed")
        for address in await _resolve(parts.hostname, port):
            if not ipaddress.ip_address(address.split("%")[0]).is_global:
                raise IngestionError("That address is not publicly reachable")
    return url


async def fetch_url(url: str) -> FetchedPage:
    settings = get_settings()
    timeout = httpx.Timeout(settings.url_fetch_timeout_seconds)
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,text/plain;q=0.9"}
    async with httpx.AsyncClient(
        timeout=timeout, follow_redirects=False, headers=headers
    ) as client:
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            await validate_url(current)
            try:
                async with client.stream("GET", current) as response:
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location:
                            raise IngestionError("The server sent an invalid redirect")
                        current = urljoin(current, location)
                        continue
                    return await _read(response, current)
            except httpx.TimeoutException as exc:
                raise IngestionError("The server took too long to respond") from exc
            except httpx.HTTPError as exc:
                raise IngestionError("The page could not be downloaded") from exc
    raise IngestionError("Too many redirects")


async def _read(response: httpx.Response, url: str) -> FetchedPage:
    if response.status_code != httpx.codes.OK:
        raise IngestionError(f"The server answered with status {response.status_code}")
    content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
    if content_type not in ACCEPTED_TYPES:
        raise IngestionError("Only HTML or plain text pages are supported")
    limit = get_settings().url_fetch_max_bytes
    body = bytearray()
    async for chunk in response.aiter_bytes():
        body.extend(chunk)
        if len(body) > limit:
            raise IngestionError("The page is too large")
    normalized = "text/plain" if content_type == "text/plain" else "text/html"
    return FetchedPage(url=url, content_type=normalized, body=bytes(body))
