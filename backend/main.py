from fastapi import FastAPI, Request
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import RequestResponseEndpoint
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse, RedirectResponse, Response

from api.rate_limit import limiter
from api.routes import make_api_exceptions, make_api_router
from settings import get_api_settings

_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": "frame-ancestors 'none'; object-src 'none'",
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
    "X-XSS-Protection": "0",
    "Permissions-Policy": (
        "clipboard-write=(self), camera=(), microphone=(), geolocation=()"
    ),
    "Cache-Control": "no-store",
    "Referrer-Policy": "strict-origin-when-cross-origin",
}


def rate_limit_exceeded(request: Request, exc: Exception) -> Response:
    limit = exc.detail if isinstance(exc, RateLimitExceeded) else "too many requests"
    response = JSONResponse(
        {"detail": f"Too many attempts. Try again later (limit: {limit})."},
        status_code=429,
    )
    return request.app.state.limiter._inject_headers(
        response, request.state.view_rate_limit
    )


def get_application() -> FastAPI:
    settings = get_api_settings()
    server = FastAPI(**settings.fastapi_kwargs)

    server.state.limiter = limiter
    server.add_exception_handler(RateLimitExceeded, rate_limit_exceeded)

    server.add_middleware(
        CORSMiddleware,  # type: ignore[arg-type]
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["Authorization", "Content-Type", "x-ciphermoth-key-derivation"],
    )

    @server.middleware("http")
    async def add_security_headers(
        request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)
        response.headers.update(_SECURITY_HEADERS)
        return response

    if not settings.disable_docs:

        @server.get("/", include_in_schema=False)
        def redirect_to_docs() -> RedirectResponse:
            return RedirectResponse(settings.docs_url)

    server.include_router(make_api_router(), prefix="/api")
    make_api_exceptions(server)

    return server


app = get_application()
