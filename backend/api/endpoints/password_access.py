from fastapi import APIRouter, Query

from api.endpoints.deps import AuthContextDep, SessionDep
from crud.access import EntryACL
from schemas import (
    EntryAccess,
    ShareGrant,
    ShareUpdatePayload,
    SimpleDetailSchema,
)

router = APIRouter(tags=["sharing"])


@router.get("/access", response_model=list[EntryAccess])
async def access_map(
    context: AuthContextDep,
    session: SessionDep,
    trash: bool = Query(default=False),
) -> list[EntryAccess]:
    return await EntryACL(session, context).access_map(deleted=trash)


@router.get("/{entry_id}/shares", response_model=list[ShareGrant])
async def list_shares(
    entry_id: int, context: AuthContextDep, session: SessionDep
) -> list[ShareGrant]:
    return await EntryACL(session, context).list_shares(entry_id)


@router.put("/{entry_id}/shares/{user_id}", response_model=ShareGrant)
async def set_share(
    entry_id: int,
    user_id: int,
    body: ShareUpdatePayload,
    context: AuthContextDep,
    session: SessionDep,
) -> ShareGrant:
    return await EntryACL(session, context).set_share(
        entry_id, user_id, body.permission
    )


@router.delete("/{entry_id}/shares/{user_id}", response_model=SimpleDetailSchema)
async def revoke_share(
    entry_id: int,
    user_id: int,
    context: AuthContextDep,
    session: SessionDep,
) -> SimpleDetailSchema:
    await EntryACL(session, context).revoke_share(entry_id, user_id)
    return SimpleDetailSchema(detail="Access revoked.")


@router.delete("/{entry_id}/access", response_model=SimpleDetailSchema)
async def relinquish(
    entry_id: int, context: AuthContextDep, session: SessionDep
) -> SimpleDetailSchema:
    await EntryACL(session, context).relinquish(entry_id)
    return SimpleDetailSchema(detail="Access relinquished.")
