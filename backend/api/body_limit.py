from starlette.exceptions import HTTPException
from starlette.formparsers import MultiPartParser
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

MAX_REQUEST_BODY_BYTES = 12 * 1024 * 1024
_TOO_LARGE = "Request is too large. The limit is 12 MB."


class RequestTooLarge(HTTPException):
    def __init__(self) -> None:
        super().__init__(status_code=413, detail=_TOO_LARGE)


def keep_uploads_in_memory(max_bytes: int = MAX_REQUEST_BODY_BYTES) -> None:
    """
    Starlette spools multipart file parts larger than 1 MB to a temporary file on
    disk, which would put attachments and imports there in plaintext. With every
    request body capped at ``max_bytes``, raising the spool threshold to the same
    value keeps each part in memory.
    """
    MultiPartParser.spool_max_size = max_bytes


def _declared_length(scope: Scope) -> int | None:
    for name, value in scope.get("headers", []):
        if name == b"content-length":
            try:
                return int(value)
            except ValueError:
                return None
    return None


class BodySizeLimitMiddleware:
    def __init__(self, app: ASGIApp, max_bytes: int = MAX_REQUEST_BODY_BYTES) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        declared = _declared_length(scope)
        if declared is not None and declared > self.max_bytes:
            response = JSONResponse(status_code=413, content={"detail": _TOO_LARGE})
            await response(scope, receive, send)
            return

        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise RequestTooLarge()
            return message

        await self.app(scope, limited_receive, send)
