from fastapi import APIRouter, FastAPI
from fastapi.exceptions import RequestValidationError

from api.endpoints import (
    health,
    master_password,
    meta,
    password,
    settings,
)
from api.exceptions import validation_handler, vault_error_handler
from api.responses import inject_responses
from errors import VaultError


def make_api_router() -> APIRouter:
    api_router = APIRouter()

    api_router.responses = inject_responses()

    api_router.include_router(master_password.router, prefix="/master_password")
    api_router.include_router(health.router, prefix="/health")
    api_router.include_router(meta.router, prefix="/meta")
    api_router.include_router(password.router, prefix="/passwords")
    api_router.include_router(settings.router, prefix="/settings")

    return api_router


def make_api_exceptions(app: FastAPI) -> None:
    app.add_exception_handler(VaultError, vault_error_handler)
    app.add_exception_handler(RequestValidationError, validation_handler)
