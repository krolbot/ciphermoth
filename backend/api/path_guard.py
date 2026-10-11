import re

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

ENCODED_SLASH_DETAIL = (
    "This request names an entry containing '/', which cannot be addressed in a "
    "URL. Edit the entry to rename it first; nothing was changed."
)
_ENCODED_SLASH = re.compile(rb"%2f", re.IGNORECASE)


class EncodedSlashGuard:
    """
    Routing matches the percent-decoded path, so an entry name containing '/'
    (sent as %2F) was matched against a different route: deleting an entry
    named 'x/purge' purged the trashed entry 'x', and 'x/attachments/1' deleted
    another entry's attachment. No API path legitimately carries an encoded
    slash, so such requests are refused before routing.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and _ENCODED_SLASH.search(
            scope.get("raw_path") or b""
        ):
            response = JSONResponse(
                status_code=400, content={"detail": ENCODED_SLASH_DETAIL}
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)
