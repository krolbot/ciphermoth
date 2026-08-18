import hashlib
from collections.abc import Callable
from typing import TypedDict

from mcp.server import MCPServer
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.exceptions import Unauthorized
from crud.auth import AuthContext, AuthCRUD
from crud.password import PasswordCRUD
from models import UserModel
from schemas import CustomField, Password, PasswordResponse, UserRole

SessionFactory = Callable[[], AsyncSession]
MCP_SCOPE = "vault"


class EntryChanges(TypedDict, total=False):
    password_name: str
    kind: str
    username: str | None
    password_value: str
    url: str | None
    totp_secret: str | None
    description: str | None
    tags: list[str]
    custom_fields: list[CustomField]
    folder: str | None
    favorite: bool


class ServiceTokenVerifier:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    async def verify_token(self, token: str) -> AccessToken | None:
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        async with self._session_factory() as session:
            user = await session.scalar(
                select(UserModel).where(
                    UserModel.service_token_hash == token_hash,
                    UserModel.role == UserRole.service,
                    UserModel.active.is_(True),
                )
            )
        if user is None:
            return None
        return AccessToken(
            token=token,
            client_id=f"ciphermoth-service-{user.id}",
            subject=str(user.id),
            scopes=[MCP_SCOPE],
            claims={},
        )


def _current_token() -> str:
    access_token = get_access_token()
    if access_token is None:
        raise Unauthorized("Authentication is required.")
    return access_token.token


async def _service_context(session: AsyncSession) -> AuthContext:
    return await AuthCRUD(session).resolve_service_token(_current_token())


def _entry_index(entry: PasswordResponse) -> dict[str, object]:
    return {
        "id": entry.id,
        "name": entry.password_name,
        "kind": entry.kind,
        "username": entry.username,
        "url": entry.url,
        "description": entry.description,
        "tags": entry.tags,
        "folder": entry.folder,
        "favorite": entry.favorite,
        "owner": entry.owner_username,
        "access": entry.access.value,
    }


def _entry_detail(entry: PasswordResponse) -> dict[str, object]:
    return entry.model_dump(
        mode="json",
        exclude={
            "owner_id",
            "backed_up",
            "deleted",
            "password_history",
            "attachment_count",
        },
    )


def build_mcp_server(session_factory: SessionFactory) -> MCPServer[None]:
    server = MCPServer(
        "ciphermoth",
        description="Access explicitly shared CipherMoth vault entries.",
    )

    @server.tool()
    async def list_entries() -> list[dict[str, object]]:
        """List metadata for vault entries shared with this service identity."""
        async with session_factory() as session:
            context = await _service_context(session)
            entries = await PasswordCRUD(session).get_passwords(context)
            return [_entry_index(entry) for entry in entries]

    @server.tool()
    async def get_entry(entry_id: int) -> dict[str, object]:
        """Read one vault entry shared with this service identity."""
        async with session_factory() as session:
            context = await _service_context(session)
            entry = await PasswordCRUD(session).get_password(entry_id, context)
            return _entry_detail(entry)

    @server.tool()
    async def create_entry(entry: Password) -> dict[str, object]:
        """Create a vault entry for this service identity's human owner."""
        async with session_factory() as session:
            try:
                context = await _service_context(session)
                created = await PasswordCRUD(session).create_password(entry, context)
                await session.commit()
                return _entry_detail(created)
            except Exception:
                await session.rollback()
                raise

    @server.tool()
    async def relinquish_entry(entry_id: int) -> dict[str, object]:
        """Remove this service identity's access while preserving the owner's entry."""
        async with session_factory() as session:
            try:
                context = await _service_context(session)
                await PasswordCRUD(session).relinquish_password(entry_id, context)
                await session.commit()
                return {"entry_id": entry_id, "relinquished": True}
            except Exception:
                await session.rollback()
                raise

    @server.tool()
    async def update_entry(entry_id: int, changes: EntryChanges) -> dict[str, object]:
        """Update fields on one entry when this service identity has write access."""
        if not changes:
            raise ValueError("At least one field must be changed.")
        async with session_factory() as session:
            try:
                context = await _service_context(session)
                crud = PasswordCRUD(session)
                current = await crud.get_password(entry_id, context)
                values = {
                    field: getattr(current, field) for field in Password.model_fields
                }
                values.update(changes)
                await crud.update_password(
                    entry_id, Password.model_validate(values), context
                )
                updated = await crud.get_password(entry_id, context)
                await session.commit()
                return _entry_detail(updated)
            except Exception:
                await session.rollback()
                raise

    return server
