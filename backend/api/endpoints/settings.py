from fastapi import APIRouter

from api.endpoints.deps import SettingsCRUDDep, VaultContextDep
from schemas import SettingsResponse, SettingsUpdate

router = APIRouter(tags=["settings"])


@router.get("", name="settings:get", response_model=SettingsResponse)
async def get_settings(
    crud: SettingsCRUDDep, context: VaultContextDep
) -> SettingsResponse:
    return await crud.get_settings(context.user.id)


@router.patch("", name="settings:update", response_model=SettingsResponse)
async def update_settings(
    body: SettingsUpdate,
    crud: SettingsCRUDDep,
    context: VaultContextDep,
) -> SettingsResponse:
    return await crud.update_settings(context.user.id, body)
