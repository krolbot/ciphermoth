from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from api.exceptions import Forbidden, Unauthorized
from crud.attachment import AttachmentCRUD
from crud.auth import AuthContext, AuthCRUD
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


SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_auth_crud(session: SessionDep) -> AuthCRUD:
    return AuthCRUD(session)


def get_password_crud(session: SessionDep) -> PasswordCRUD:
    return PasswordCRUD(session)


def get_settings_crud(session: SessionDep) -> SettingsCRUD:
    return SettingsCRUD(session)


def get_attachment_crud(session: SessionDep) -> AttachmentCRUD:
    return AttachmentCRUD(session)


AuthCRUDDep = Annotated[AuthCRUD, Depends(get_auth_crud)]
PasswordCRUDDep = Annotated[PasswordCRUD, Depends(get_password_crud)]
SettingsCRUDDep = Annotated[SettingsCRUD, Depends(get_settings_crud)]
AttachmentCRUDDep = Annotated[AttachmentCRUD, Depends(get_attachment_crud)]


async def get_auth_context(
    crud: AuthCRUDDep,
    authorization: Annotated[str | None, Header()] = None,
    x_ciphermoth_key_derivation: Annotated[str | None, Header()] = None,
) -> AuthContext:
    if not authorization or not authorization.startswith("Bearer "):
        raise Unauthorized("Authentication is required.")
    if not x_ciphermoth_key_derivation:
        raise Unauthorized("User key is missing.")
    return await crud.resolve_session(
        authorization.removeprefix("Bearer "), x_ciphermoth_key_derivation
    )


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
