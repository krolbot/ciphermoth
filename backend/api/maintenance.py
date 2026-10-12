from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from crud.updates import maintenance_active

ALLOWED_DURING_MAINTENANCE = {
    ("GET", "/api/meta"),
    ("GET", "/api/master_password/status"),
    ("GET", "/api/health"),
    ("GET", "/api/updates/apply/status"),
}


class MaintenanceMode:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] == "http"
            and scope["method"] != "OPTIONS"
            and (scope["method"], scope["path"]) not in ALLOWED_DURING_MAINTENANCE
            and maintenance_active()
        ):
            response = JSONResponse(
                {
                    "detail": "CipherMoth is installing an update. Try again in a "
                    "minute.",
                    "code": "maintenance",
                },
                status_code=503,
                headers={"Retry-After": "30"},
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)
