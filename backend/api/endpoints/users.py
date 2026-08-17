from fastapi import APIRouter

from api.endpoints.deps import AdminContextDep, AuthCRUDDep, VaultContextDep
from crud.auth import decode_auth_key_material, decode_client_key_material
from schemas import (
    AuthUser,
    ShareTarget,
    UserCreatePayload,
    UserCreateResponse,
    UserRole,
    UserUpdatePayload,
)

router = APIRouter(tags=["users"])


@router.get("/share-targets", response_model=list[ShareTarget])
async def list_share_targets(
    context: VaultContextDep, crud: AuthCRUDDep
) -> list[ShareTarget]:
    return await crud.list_share_targets(context.user)


@router.get("", response_model=list[AuthUser])
async def list_users(context: AdminContextDep, crud: AuthCRUDDep) -> list[AuthUser]:
    return await crud.list_users(context.user)


@router.post("", response_model=UserCreateResponse)
async def create_user(
    payload: UserCreatePayload,
    context: AdminContextDep,
    crud: AuthCRUDDep,
) -> UserCreateResponse:
    key_material = (
        decode_client_key_material(
            payload.salt, payload.public_key, payload.encrypted_private_key
        )
        if payload.role != UserRole.service
        and payload.salt is not None
        and payload.public_key is not None
        and payload.encrypted_private_key is not None
        else (None, None, None)
    )
    auth_key_material = (
        decode_auth_key_material(
            payload.auth_public_key, payload.encrypted_auth_private_key
        )
        if payload.role != UserRole.service
        and payload.auth_public_key is not None
        and payload.encrypted_auth_private_key is not None
        else (None, None)
    )
    return await crud.create_user(
        context.user,
        username=payload.username,
        role=payload.role,
        salt=key_material[0],
        public_key=key_material[1],
        encrypted_private_key=key_material[2],
        auth_public_key=auth_key_material[0],
        encrypted_auth_private_key=auth_key_material[1],
    )


@router.patch("/{user_id}", response_model=AuthUser)
async def update_user(
    user_id: int,
    payload: UserUpdatePayload,
    context: AdminContextDep,
    crud: AuthCRUDDep,
) -> AuthUser:
    return await crud.update_user(
        context.user, user_id, role=payload.role, active=payload.active
    )
