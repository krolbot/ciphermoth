from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from crud.base import BaseCRUD
from crud.engine import after_commit, after_rollback
from crud.master_password import MasterPasswordCRUD
from crud.settings import SettingsCRUD
from errors import InvalidKey, SessionRequired
from schemas import (
    MasterPasswordCreate,
    MasterPasswordUpdate,
    VaultSessionStatus,
    VaultUnlock,
)
from vault_sessions import VaultSessions, idle_timeout_for

_SESSION_ENDED = "Your session expired or was locked. Unlock the vault again."


@dataclass(frozen=True, slots=True)
class SessionToken:
    token: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class LegacyKey:
    key: str = field(repr=False)


Credential = SessionToken | LegacyKey


class VaultAccess(BaseCRUD):
    """
    Turns a master password into a vault session and a session back into the
    vault key, for one request. Every use of a session still checks its key
    against the vault's key check under the shared row lock, exactly like the
    legacy key header, so a session can never outlive the key it was opened
    with, whichever process or release changed it.
    """

    def __init__(self, session: AsyncSession, vault_sessions: VaultSessions) -> None:
        super().__init__(session)
        self.vault_sessions = vault_sessions
        self.master_password = MasterPasswordCRUD(session)

    async def _refresh_idle_timeout(self) -> None:
        inactivity_ms = await SettingsCRUD(
            self.session, self.vault_sessions
        ).inactivity_ms()
        self.vault_sessions.set_idle_timeout(idle_timeout_for(inactivity_ms))

    def _open(self, key: str) -> str:
        token = self.vault_sessions.open(key)
        after_rollback(self.session, lambda: self.vault_sessions.revoke(token))
        return token

    async def unlock(self, master_password: str) -> VaultUnlock:
        key = await self.master_password.unlock(master_password)
        if key is None:
            return VaultUnlock(valid=False)
        await self._refresh_idle_timeout()
        return VaultUnlock(
            valid=True,
            session_token=self._open(key),
            idle_timeout_ms=self.vault_sessions.idle_timeout_ms,
        )

    async def create(self, master_password: str) -> MasterPasswordCreate:
        key = await self.master_password.create_master_password(master_password)
        await self._refresh_idle_timeout()
        return MasterPasswordCreate(
            created=True,
            detail="Master password created successfully.",
            session_token=self._open(key),
            idle_timeout_ms=self.vault_sessions.idle_timeout_ms,
        )

    async def authorize(
        self, credential: Credential, *, exclusive: bool = False
    ) -> str:
        if isinstance(credential, LegacyKey):
            return await self.master_password.verify_vault_key(
                credential.key, exclusive=exclusive
            )
        key = self.vault_sessions.resolve(credential.token)
        try:
            return await self.master_password.verify_vault_key(key, exclusive=exclusive)
        except InvalidKey:
            self.vault_sessions.revoke(credential.token)
            raise SessionRequired(_SESSION_ENDED) from None

    def status(self, credential: Credential) -> VaultSessionStatus:
        if isinstance(credential, LegacyKey):
            return VaultSessionStatus(
                idle_timeout_ms=self.vault_sessions.idle_timeout_ms,
                expires_in_ms=None,
            )
        info = self.vault_sessions.info(credential.token)
        return VaultSessionStatus(
            idle_timeout_ms=info.idle_timeout_ms, expires_in_ms=info.expires_in_ms
        )

    async def change_master_password(
        self, master_password: str, new_master_password: str
    ) -> MasterPasswordUpdate:
        result = await self.master_password.update_master_password(
            master_password, new_master_password
        )
        after_commit(self.session, self.vault_sessions.revoke_all)
        return result
