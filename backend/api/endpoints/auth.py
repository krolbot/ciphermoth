import base64

from fastapi import APIRouter, Request

from api.endpoints.deps import AuthContextDep, AuthCRUDDep
from api.rate_limit import limiter, rate
from crud.auth import (
    decode_auth_key_material,
    decode_client_key_material,
    decode_signature,
)
from schemas import (
    AuthBootstrapPayload,
    AuthChallengePayload,
    AuthChallengeResponse,
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
    salt, public_key, encrypted_private_key = decode_client_key_material(
        payload.salt, payload.public_key, payload.encrypted_private_key
    )
    auth_public_key, encrypted_auth_private_key = decode_auth_key_material(
        payload.auth_public_key, payload.encrypted_auth_private_key
    )
    return await crud.bootstrap(
        payload.username,
        salt=salt,
        public_key=public_key,
        encrypted_private_key=encrypted_private_key,
        auth_public_key=auth_public_key,
        encrypted_auth_private_key=encrypted_auth_private_key,
        legacy_migration_token=payload.legacy_migration_token,
    )


@router.post("/challenge", response_model=AuthChallengeResponse)
@limiter.limit(rate("10/minute"))
async def challenge(
    request: Request, payload: AuthChallengePayload, crud: AuthCRUDDep
) -> AuthChallengeResponse:
    return await crud.create_challenge(payload.username)


@router.post("/login", response_model=AuthSessionResponse)
@limiter.limit(rate("10/minute"))
async def login(
    request: Request, payload: AuthLoginPayload, crud: AuthCRUDDep
) -> AuthSessionResponse:
    auth_public_key = encrypted_auth_private_key = None
    if (
        payload.auth_public_key is not None
        or payload.encrypted_auth_private_key is not None
    ):
        auth_public_key, encrypted_auth_private_key = decode_auth_key_material(
            payload.auth_public_key or "", payload.encrypted_auth_private_key or ""
        )
    return await crud.login(
        payload.challenge,
        decode_signature(payload.signature),
        auth_public_key=auth_public_key,
        encrypted_auth_private_key=encrypted_auth_private_key,
    )


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
    salt, _, encrypted_private_key = decode_client_key_material(
        payload.new_salt,
        base64.urlsafe_b64encode(context.user.public_key).decode().rstrip("="),
        payload.encrypted_private_key,
    )
    _, encrypted_auth_private_key = decode_auth_key_material(
        base64.urlsafe_b64encode(context.user.auth_public_key or b"")
        .decode()
        .rstrip("="),
        payload.encrypted_auth_private_key,
    )
    return await crud.change_password(
        context,
        new_salt=salt,
        encrypted_private_key=encrypted_private_key,
        encrypted_auth_private_key=encrypted_auth_private_key,
        proof=decode_signature(payload.proof),
    )
