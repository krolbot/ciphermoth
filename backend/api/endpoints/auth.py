import base64

from fastapi import APIRouter, Request

from api.endpoints.deps import (
    AuthContextDep,
    AuthCRUDDep,
    CredentialDep,
    PasswordChangeContextDep,
    VaultSessionsDep,
)
from api.rate_limit import limiter, rate
from schemas import (
    AuthBootstrapPayload,
    AuthPayload,
    AuthResponse,
    AuthStatus,
    AuthUser,
    EntryDraftKey,
    PasswordChangePayload,
    SimpleDetailSchema,
)

router = APIRouter(tags=["auth"])


@router.get("/status", response_model=AuthStatus)
async def status(crud: AuthCRUDDep) -> AuthStatus:
    return await crud.status()


@router.post("/bootstrap", response_model=AuthResponse)
@limiter.limit(rate("5/hour"))
async def bootstrap(
    request: Request, body: AuthBootstrapPayload, crud: AuthCRUDDep
) -> AuthResponse:
    return await crud.bootstrap(body.username, body.password)


@router.post("/login", response_model=AuthResponse)
@limiter.limit(rate("30/hour"))
async def login(request: Request, body: AuthPayload, crud: AuthCRUDDep) -> AuthResponse:
    return await crud.login(body.username, body.password)


@router.get("/me", response_model=AuthUser)
async def me(context: PasswordChangeContextDep, crud: AuthCRUDDep) -> AuthUser:
    return crud.to_user(context.user)


@router.post("/logout", response_model=SimpleDetailSchema)
async def logout(
    credential: CredentialDep, vault_sessions: VaultSessionsDep
) -> SimpleDetailSchema:
    vault_sessions.revoke(credential.token)
    return SimpleDetailSchema(detail="Logged out.")


@router.get("/entry-draft-key", response_model=EntryDraftKey)
async def entry_draft_key(context: AuthContextDep) -> EntryDraftKey:
    return EntryDraftKey(
        user_id=context.user.id,
        key=base64.b64encode(context.key.entry_draft_key(context.user.id)).decode(),
    )


@router.put("/password", response_model=AuthResponse)
@limiter.limit(rate("10/hour"))
async def change_password(
    request: Request,
    body: PasswordChangePayload,
    context: PasswordChangeContextDep,
    crud: AuthCRUDDep,
) -> AuthResponse:
    return await crud.change_password(context, body.current_password, body.new_password)
