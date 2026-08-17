from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from mcp.server.auth.middleware.auth_context import AuthContextMiddleware
from mcp.server.auth.middleware.bearer_auth import (
    BearerAuthBackend,
    RequireAuthMiddleware,
)
from mcp.server.transport_security import TransportSecuritySettings
from slowapi.errors import RateLimitExceeded
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.middleware.base import RequestResponseEndpoint
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse, RedirectResponse, Response

from api.rate_limit import limiter
from api.routes import make_api_exceptions, make_api_router
from crud.session import AsyncSessionLocal
from mcp_server import MCP_SCOPE, ServiceTokenVerifier, SessionFactory, build_mcp_server
from settings import APISettings, get_api_settings

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


def get_application(
    *,
    api_settings: APISettings | None = None,
    session_factory: SessionFactory = AsyncSessionLocal,
) -> FastAPI:
    settings = api_settings or get_api_settings()
    mcp = build_mcp_server(session_factory)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        async with mcp.session_manager.run():
            yield

    server = FastAPI(**settings.fastapi_kwargs, lifespan=lifespan)

    server.state.limiter = limiter
    server.add_exception_handler(RateLimitExceeded, rate_limit_exceeded)

    server.add_middleware(
        CORSMiddleware,  # type: ignore[arg-type]
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["Authorization", "Content-Type"],
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

    mcp_app = mcp.streamable_http_app(
        stateless_http=True,
        json_response=True,
        max_request_body_size=settings.mcp_max_request_bytes,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=False
        ),
    )
    mcp_app = AuthenticationMiddleware(
        AuthContextMiddleware(RequireAuthMiddleware(mcp_app, [MCP_SCOPE])),
        backend=BearerAuthBackend(ServiceTokenVerifier(session_factory)),
    )
    server.mount("/", mcp_app)
    server.state.mcp_server = mcp

    return server


app = get_application()
