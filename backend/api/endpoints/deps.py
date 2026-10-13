from collections.abc import AsyncGenerator
from typing import Annotated
from urllib.parse import unquote

from fastapi import Depends, Header, Path, Request
from fastapi.security import APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession

from api.path_guard import entry_name
from crud.attachment import AttachmentCRUD
from crud.engine import Database
from crud.master_password import MasterPasswordCRUD
from crud.password import PasswordCRUD
from crud.settings import SettingsCRUD
from crud.vault_access import SessionToken, VaultAccess
from errors import Forbidden, InvalidRequest, SessionRequired
from vault_sessions import VaultSessions

SESSION_HEADER = "x-ciphermoth-session"
_session_header = APIKeyHeader(
    name=SESSION_HEADER,
    auto_error=False,
    description="A vault session token from POST /master_password/unlock.",
)


async def get_database(request: Request) -> Database:
    return request.app.state.database


async def get_vault_sessions(request: Request) -> VaultSessions:
    return request.app.state.vault_sessions


VaultSessionsDep = Annotated[VaultSessions, Depends(get_vault_sessions)]


async def get_session(
    database: Annotated[Database, Depends(get_database)],
) -> AsyncGenerator[AsyncSession]:
    async with database.transaction() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session, scope="function")]


async def get_master_password_crud(session: SessionDep) -> MasterPasswordCRUD:
    return MasterPasswordCRUD(session)


async def get_password_crud(session: SessionDep) -> PasswordCRUD:
    return PasswordCRUD(session)


async def get_settings_crud(
    session: SessionDep, vault_sessions: VaultSessionsDep
) -> SettingsCRUD:
    return SettingsCRUD(session, vault_sessions)


async def get_attachment_crud(session: SessionDep) -> AttachmentCRUD:
    return AttachmentCRUD(session)


async def get_vault_access(
    session: SessionDep, vault_sessions: VaultSessionsDep
) -> VaultAccess:
    return VaultAccess(session, vault_sessions)


MasterPasswordCRUDDep = Annotated[MasterPasswordCRUD, Depends(get_master_password_crud)]
PasswordCRUDDep = Annotated[PasswordCRUD, Depends(get_password_crud)]
SettingsCRUDDep = Annotated[SettingsCRUD, Depends(get_settings_crud)]
AttachmentCRUDDep = Annotated[AttachmentCRUD, Depends(get_attachment_crud)]
VaultAccessDep = Annotated[VaultAccess, Depends(get_vault_access)]
SessionTokenHeader = Annotated[str | None, Depends(_session_header)]


async def get_credential(token: SessionTokenHeader) -> SessionToken:
    """
    The session token a request carries in the ``x-ciphermoth-session`` header.
    ``Authorization`` is left alone, so a reverse proxy can still put its own
    authentication in front of the vault.
    """
    if token is None:
        raise SessionRequired("The vault is locked. Unlock it first.")
    return SessionToken(token)


CredentialDep = Annotated[SessionToken, Depends(get_credential)]


async def get_vault_key(access: VaultAccessDep, credential: CredentialDep) -> str:
    return await access.authorize(credential)


async def get_vault_key_quietly(
    access: VaultAccessDep, credential: CredentialDep
) -> str:
    return await access.authorize(credential, refresh=False)


async def get_vault_key_for_rotation(
    access: VaultAccessDep, credential: CredentialDep
) -> str:
    return await access.authorize(credential, exclusive=True)


VaultKeyDep = Annotated[str, Depends(get_vault_key)]
_PATH_CHANGED = (
    "The entry name in the request path was changed before it reached "
    "CipherMoth, so nothing was done. A reverse proxy in front of the API is "
    "probably decoding %2F; configure it to pass the request path unchanged."
)


async def get_entry_name(
    password_name: Annotated[str, Path()],
    x_ciphermoth_entry: Annotated[str | None, Header()] = None,
) -> str:
    """
    The entry a request names. Current clients also send the intended name in
    the x-ciphermoth-entry header, percent-encoded, because a reverse proxy
    that decodes %2F would turn the name 'x/purge' into a request to purge the
    entry 'x' and the server cannot tell from the path alone. When the header
    is present and does not match, the request is refused.
    """
    name = entry_name(password_name)
    if x_ciphermoth_entry is not None and unquote(x_ciphermoth_entry) != name:
        raise InvalidRequest(_PATH_CHANGED)
    return name


EntryName = Annotated[str, Depends(get_entry_name)]


async def require_master_password(crud: MasterPasswordCRUDDep) -> None:
    if not await crud.is_initialized():
        raise Forbidden("No master password set.")
