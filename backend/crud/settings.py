from sqlalchemy import select

from crud.base import BaseCRUD
from models import SETTINGS_DEFAULTS, SettingsModel
from schemas import SettingsResponse, SettingsUpdate


class SettingsCRUD(BaseCRUD):
    async def _get_or_create(self, user_id: int) -> SettingsModel:
        model = await self.session.scalar(
            select(SettingsModel).where(SettingsModel.user_id == user_id)
        )
        if model is None:
            model = SettingsModel(user_id=user_id, **SETTINGS_DEFAULTS)
            self.session.add(model)
            await self.session.flush()
        return model

    @staticmethod
    def _to_response(model: SettingsModel) -> SettingsResponse:
        return SettingsResponse(
            inactivity_ms=model.inactivity_ms,
            warn_before_ms=model.warn_before_ms,
            hidden_ms=model.hidden_ms,
            debounce_ms=model.debounce_ms,
            clipboard_clear_ms=model.clipboard_clear_ms,
            update_check_enabled=model.update_check_enabled,
        )

    async def get_settings(self, user_id: int) -> SettingsResponse:
        return self._to_response(await self._get_or_create(user_id))

    async def update_settings(
        self, user_id: int, data: SettingsUpdate
    ) -> SettingsResponse:
        model = await self._get_or_create(user_id)
        for field, value in data.model_dump().items():
            setattr(model, field, value)
        self.session.add(model)
        await self.session.flush()
        return self._to_response(model)
