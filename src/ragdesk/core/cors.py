"""CORS for the public widget endpoints.

The admin API uses the regular `CORSMiddleware` with a fixed list of origins. The widget runs on
customers' websites, so its origin is not known in advance: this middleware answers any origin on
the public path and the route itself enforces the bot's allowed-origins list (403). No cookies are
involved (`Access-Control-Allow-Credentials` is never sent).
"""

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

ALLOWED_METHODS = "GET, POST, OPTIONS"
ALLOWED_HEADERS = "Content-Type, Accept"
PREFLIGHT_MAX_AGE = "600"


class PublicCorsMiddleware:
    def __init__(self, app: ASGIApp, *, path_prefix: str) -> None:
        self.app = app
        self.path_prefix = path_prefix

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith(self.path_prefix):
            await self.app(scope, receive, send)
            return

        origin = Headers(scope=scope).get("origin")
        if origin is None:
            await self.app(scope, receive, send)
            return

        if scope["method"] == "OPTIONS":
            headers = {
                "Access-Control-Allow-Origin": origin,
                "Access-Control-Allow-Methods": ALLOWED_METHODS,
                "Access-Control-Allow-Headers": ALLOWED_HEADERS,
                "Access-Control-Max-Age": PREFLIGHT_MAX_AGE,
                "Vary": "Origin",
            }
            await Response(status_code=204, headers=headers)(scope, receive, send)
            return

        async def send_with_cors(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["Access-Control-Allow-Origin"] = origin
                headers.append("Vary", "Origin")
            await send(message)

        await self.app(scope, receive, send_with_cors)
