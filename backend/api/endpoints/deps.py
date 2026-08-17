from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from api.exceptions import Forbidden, Unauthorized
from crud.auth import AuthContext, AuthCRUD
from crud.encrypted_password import EncryptedPasswordCRUD
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


SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_auth_crud(session: SessionDep) -> AuthCRUD:
    return AuthCRUD(session)


def get_encrypted_password_crud(session: SessionDep) -> EncryptedPasswordCRUD:
    return EncryptedPasswordCRUD(session)


def get_settings_crud(session: SessionDep) -> SettingsCRUD:
    return SettingsCRUD(session)


AuthCRUDDep = Annotated[AuthCRUD, Depends(get_auth_crud)]
EncryptedPasswordCRUDDep = Annotated[
    EncryptedPasswordCRUD, Depends(get_encrypted_password_crud)
]
SettingsCRUDDep = Annotated[SettingsCRUD, Depends(get_settings_crud)]


async def get_auth_context(
    crud: AuthCRUDDep,
    authorization: Annotated[str | None, Header()] = None,
) -> AuthContext:
    if not authorization or not authorization.startswith("Bearer "):
        raise Unauthorized("Authentication is required.")
    return await crud.resolve_session(authorization.removeprefix("Bearer "))


AuthContextDep = Annotated[AuthContext, Depends(get_auth_context)]


def require_vault_context(context: AuthContextDep) -> AuthContext:
    if context.user.must_change_password:
        raise Forbidden("Master password change is required.")
    return context


VaultContextDep = Annotated[AuthContext, Depends(require_vault_context)]


def require_admin_context(context: VaultContextDep) -> AuthContext:
    if context.user.role != "admin":
        raise Forbidden("Administrator access is required.")
    return context


AdminContextDep = Annotated[AuthContext, Depends(require_admin_context)]
