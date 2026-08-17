from fastapi import APIRouter, FastAPI

from api.endpoints import (
    auth,
    meta,
    password,
    settings,
    updates,
    users,
)
from api.exceptions import (
    Forbidden,
    NotFound,
    TypesMismatchError,
    Unauthorized,
    forbidden_handler,
    internal_error_handler,
    mismatch_handler,
    not_found_handler,
    unauthorized_handler,
)
from api.responses import inject_responses


def make_api_router() -> APIRouter:
    api_router = APIRouter()
    api_router.include_router(auth.router, prefix="/auth")
    api_router.include_router(users.router, prefix="/users")

    api_router.responses = inject_responses()

    api_router.include_router(meta.router, prefix="/meta")
    api_router.include_router(password.router, prefix="/passwords")
    api_router.include_router(settings.router, prefix="/settings")
    api_router.include_router(updates.router, prefix="/updates")

    return api_router


def make_api_exceptions(app: FastAPI) -> None:
    app.add_exception_handler(Forbidden, forbidden_handler)
    app.add_exception_handler(Unauthorized, unauthorized_handler)
    app.add_exception_handler(NotFound, not_found_handler)
    app.add_exception_handler(TypesMismatchError, mismatch_handler)
    app.add_exception_handler(Exception, internal_error_handler)
