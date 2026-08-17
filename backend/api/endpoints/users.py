from fastapi import APIRouter

from api.endpoints.deps import AdminContextDep, AuthCRUDDep, VaultContextDep
from schemas import AuthUser, ShareTarget, UserCreatePayload, UserUpdatePayload

router = APIRouter(tags=["users"])


@router.get("/share-targets", response_model=list[ShareTarget])
async def list_share_targets(
    context: VaultContextDep, crud: AuthCRUDDep
) -> list[ShareTarget]:
    return await crud.list_share_targets(context.user)


@router.get("", response_model=list[AuthUser])
async def list_users(context: AdminContextDep, crud: AuthCRUDDep) -> list[AuthUser]:
    return await crud.list_users(context.user)


@router.post("", response_model=AuthUser)
async def create_user(
    payload: UserCreatePayload,
    context: AdminContextDep,
    crud: AuthCRUDDep,
) -> AuthUser:
    return await crud.create_user(
        context.user,
        username=payload.username,
        temporary_password=payload.temporary_password,
        role=payload.role,
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
