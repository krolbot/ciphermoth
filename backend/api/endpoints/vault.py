from typing import Literal

from fastapi import APIRouter, Depends, status

from api.endpoints.deps import DamageCRUDDep, VaultKeyDep, require_master_password
from api.responses import inject_responses
from schemas import DamagedRows, PasswordDelete, SimpleDetailSchema

router = APIRouter(tags=["vault"], dependencies=[Depends(require_master_password)])


@router.get(
    "/damaged",
    name="vault:damaged",
    response_model=DamagedRows,
    responses=inject_responses({status.HTTP_403_FORBIDDEN: SimpleDetailSchema}),
)
async def get_damaged(crud: DamageCRUDDep, key: VaultKeyDep) -> DamagedRows:
    return await crud.find(key)


@router.delete(
    "/damaged/{kind}/{row_id}",
    name="vault:remove-damaged",
    response_model=PasswordDelete,
    responses=inject_responses(
        {
            status.HTTP_400_BAD_REQUEST: SimpleDetailSchema,
            status.HTTP_403_FORBIDDEN: SimpleDetailSchema,
            status.HTTP_404_NOT_FOUND: SimpleDetailSchema,
        }
    ),
)
async def remove_damaged(
    kind: Literal["entries", "attachments"],
    row_id: int,
    crud: DamageCRUDDep,
    key: VaultKeyDep,
) -> PasswordDelete:
    return await crud.remove(key, kind, row_id)
