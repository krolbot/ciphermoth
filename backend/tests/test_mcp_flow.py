import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from crud.auth import AuthCRUD
from crud.password import PasswordCRUD
from main import get_application
from models import BaseModel, InstanceStateModel, UserModel
from schemas import Password, SharePermission, UserRole
from settings import APISettings


async def _post_mcp(
    client: httpx.AsyncClient,
    token: str,
    payload: dict[str, object],
    protocol_version: str | None = None,
) -> httpx.Response:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    if protocol_version:
        headers["MCP-Protocol-Version"] = protocol_version
    return await client.post("/mcp", headers=headers, json=payload)


@pytest.mark.asyncio
async def test_mcp_uses_service_identity_and_existing_entry_acl() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(BaseModel.metadata.create_all)

    async with maker() as session:
        session.add(InstanceStateModel(id=1))
        await session.flush()
        auth = AuthCRUD(session)
        owner_login = await auth.bootstrap("owner", "correct horse battery staple")
        owner_context = await auth.resolve_session(
            owner_login.token, owner_login.key_derivation
        )
        service = await auth.create_user(
            owner_context.user,
            username="future-ai",
            temporary_password=None,
            role=UserRole.service,
        )
        assert service.service_token is not None
        service_model = await session.get(UserModel, service.id)
        assert service_model is not None
        created = await PasswordCRUD(session).create_password(
            Password(
                password_name="shared",
                password_value="secret",
                url="https://example.com",
                tags=["production"],
            ),
            owner_context,
        )
        await PasswordCRUD(session).set_share(
            created.id, service.id, SharePermission.read, owner_context
        )
        await session.commit()
        token = service.service_token
        entry_id = created.id

    application = get_application(api_settings=APISettings(), session_factory=maker)
    transport = httpx.ASGITransport(app=application)
    async with application.router.lifespan_context(application):
        async with httpx.AsyncClient(
            transport=transport, base_url="https://public.example"
        ) as client:
            unauthorized = await client.post(
                "/mcp",
                json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            )
            assert unauthorized.status_code == 401

            initialized = await _post_mcp(
                client,
                token,
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-03-26",
                        "capabilities": {},
                        "clientInfo": {"name": "test", "version": "1"},
                    },
                },
            )
            assert initialized.status_code == 200
            protocol_version = initialized.json()["result"]["protocolVersion"]

            tools = await _post_mcp(
                client,
                token,
                {"jsonrpc": "2.0", "id": 3, "method": "tools/list"},
                protocol_version,
            )
            assert [tool["name"] for tool in tools.json()["result"]["tools"]] == [
                "list_entries",
                "get_entry",
                "update_entry",
            ]

            listed = await _post_mcp(
                client,
                token,
                {
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "tools/call",
                    "params": {"name": "list_entries", "arguments": {}},
                },
                protocol_version,
            )
            assert listed.json()["result"]["structuredContent"]["result"] == [
                {
                    "id": entry_id,
                    "name": "shared",
                    "kind": "login",
                    "username": None,
                    "url": "https://example.com",
                    "description": None,
                    "tags": ["production"],
                    "folder": None,
                    "favorite": False,
                    "owner": "owner",
                    "access": "read",
                }
            ]

            read = await _post_mcp(
                client,
                token,
                {
                    "jsonrpc": "2.0",
                    "id": 5,
                    "method": "tools/call",
                    "params": {
                        "name": "get_entry",
                        "arguments": {"entry_id": entry_id},
                    },
                },
                protocol_version,
            )
            assert read.json()["result"]["structuredContent"]["password_value"] == (
                "secret"
            )

            denied = await _post_mcp(
                client,
                token,
                {
                    "jsonrpc": "2.0",
                    "id": 6,
                    "method": "tools/call",
                    "params": {
                        "name": "update_entry",
                        "arguments": {
                            "entry_id": entry_id,
                            "changes": {"password_value": "changed"},
                        },
                    },
                },
                protocol_version,
            )
            assert denied.json()["result"]["isError"] is True

            async with maker() as session:
                auth = AuthCRUD(session)
                owner_context = await auth.resolve_session(
                    owner_login.token, owner_login.key_derivation
                )
                await PasswordCRUD(session).set_share(
                    entry_id, service.id, SharePermission.write, owner_context
                )
                await session.commit()

            changed = await _post_mcp(
                client,
                token,
                {
                    "jsonrpc": "2.0",
                    "id": 7,
                    "method": "tools/call",
                    "params": {
                        "name": "update_entry",
                        "arguments": {
                            "entry_id": entry_id,
                            "changes": {"password_value": "changed"},
                        },
                    },
                },
                protocol_version,
            )
            assert changed.json()["result"].get("isError", False) is False

            reread = await _post_mcp(
                client,
                token,
                {
                    "jsonrpc": "2.0",
                    "id": 8,
                    "method": "tools/call",
                    "params": {
                        "name": "get_entry",
                        "arguments": {"entry_id": entry_id},
                    },
                },
                protocol_version,
            )
            assert reread.json()["result"]["structuredContent"]["password_value"] == (
                "changed"
            )
            assert reread.json()["result"]["structuredContent"]["url"] == (
                "https://example.com"
            )
            assert reread.json()["result"]["structuredContent"]["tags"] == [
                "production"
            ]

            async with maker() as session:
                auth = AuthCRUD(session)
                owner_context = await auth.resolve_session(
                    owner_login.token, owner_login.key_derivation
                )
                await auth.update_user(owner_context.user, service.id, active=False)
                await session.commit()

            revoked = await _post_mcp(
                client,
                token,
                {"jsonrpc": "2.0", "id": 9, "method": "tools/list"},
                protocol_version,
            )
            assert revoked.status_code == 401

    await engine.dispose()
