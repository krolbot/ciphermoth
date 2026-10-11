from collections.abc import AsyncGenerator
from typing import Annotated
from urllib.parse import unquote

from fastapi import Depends, Header, Path
from sqlalchemy.ext.asyncio import AsyncSession

from api.exceptions import Forbidden, TypesMismatchError
from api.path_guard import entry_name
from crud.attachment import AttachmentCRUD
from crud.master_password import MasterPasswordCRUD
from crud.password import PasswordCRUD
from crud.session import AsyncSessionLocal
from crud.settings import SettingsCRUD


async def get_session() -> AsyncGenerator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


SessionDep = Annotated[AsyncSession, Depends(get_session, scope="function")]


def get_master_password_crud(session: SessionDep) -> MasterPasswordCRUD:
    return MasterPasswordCRUD(session)


def get_password_crud(session: SessionDep) -> PasswordCRUD:
    return PasswordCRUD(session)


def get_settings_crud(session: SessionDep) -> SettingsCRUD:
    return SettingsCRUD(session)


def get_attachment_crud(session: SessionDep) -> AttachmentCRUD:
    return AttachmentCRUD(session)


MasterPasswordCRUDDep = Annotated[MasterPasswordCRUD, Depends(get_master_password_crud)]
PasswordCRUDDep = Annotated[PasswordCRUD, Depends(get_password_crud)]
SettingsCRUDDep = Annotated[SettingsCRUD, Depends(get_settings_crud)]
AttachmentCRUDDep = Annotated[AttachmentCRUD, Depends(get_attachment_crud)]


async def get_key_derivation(
    crud: MasterPasswordCRUDDep,
    x_ciphermoth_key_derivation: Annotated[str | None, Header()] = None,
) -> str:
    return await crud.verify_vault_key(x_ciphermoth_key_derivation)


async def get_key_derivation_for_rotation(
    crud: MasterPasswordCRUDDep,
    x_ciphermoth_key_derivation: Annotated[str | None, Header()] = None,
) -> str:
    return await crud.verify_vault_key(x_ciphermoth_key_derivation, exclusive=True)


KeyDerivationDep = Annotated[str, Depends(get_key_derivation)]
_PATH_CHANGED = (
    "The entry name in the request path was changed before it reached "
    "CipherMoth, so nothing was done. A reverse proxy in front of the API is "
    "probably decoding %2F; configure it to pass the request path unchanged."
)


def get_entry_name(
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
        raise TypesMismatchError(_PATH_CHANGED)
    return name


EntryName = Annotated[str, Depends(get_entry_name)]


async def require_master_password(crud: MasterPasswordCRUDDep) -> None:
    if not await crud.is_initialized():
        raise Forbidden("No master password set.")
