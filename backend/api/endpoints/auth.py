from fastapi import APIRouter, Request

from api.endpoints.deps import AuthContextDep, AuthCRUDDep
from api.rate_limit import limiter, rate
from schemas import (
    AuthBootstrapPayload,
    AuthLoginPayload,
    AuthSessionResponse,
    AuthStatus,
    AuthUser,
    PasswordChangePayload,
    SimpleDetailSchema,
)

router = APIRouter(tags=["auth"])


@router.get("/status", response_model=AuthStatus)
async def get_status(crud: AuthCRUDDep) -> AuthStatus:
    return await crud.status()


@router.post("/bootstrap", response_model=AuthSessionResponse)
@limiter.limit(rate("5/minute"))
async def bootstrap(
    request: Request, payload: AuthBootstrapPayload, crud: AuthCRUDDep
) -> AuthSessionResponse:
    return await crud.bootstrap(payload.username, payload.master_password)


@router.post("/login", response_model=AuthSessionResponse)
@limiter.limit(rate("10/minute"))
async def login(
    request: Request, payload: AuthLoginPayload, crud: AuthCRUDDep
) -> AuthSessionResponse:
    return await crud.login(payload.username, payload.master_password)


@router.get("/me", response_model=AuthUser)
async def me(context: AuthContextDep, crud: AuthCRUDDep) -> AuthUser:
    return crud._to_user(context.user)


@router.post("/logout", response_model=SimpleDetailSchema)
async def logout(context: AuthContextDep, crud: AuthCRUDDep) -> SimpleDetailSchema:
    await crud.logout(context.token_hash)
    return SimpleDetailSchema(detail="Logged out.")


@router.put("/password", response_model=AuthSessionResponse)
async def change_password(
    payload: PasswordChangePayload,
    context: AuthContextDep,
    crud: AuthCRUDDep,
) -> AuthSessionResponse:
    return await crud.change_password(
        context, payload.current_password, payload.new_password
    )
