import base64
import json

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from crud.auth import AuthContext, AuthCRUD
from crud.encrypted_password import EncryptedPasswordCRUD
from helpers import encrypt, generate_entry_key, wrap_entry_key
from main import get_application
from models import BaseModel, InstanceStateModel, PasswordAccessModel, UserModel
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
        owner_model = UserModel(
            username="owner",
            role="admin",
            salt=b"0" * 16,
            public_key=b"1" * 32,
            encrypted_private_key=b"unused",
        )
        session.add(owner_model)
        await session.flush()
        owner_context = AuthContext(
            user=owner_model, private_key=None, token_hash="owner-session"
        )
        auth = AuthCRUD(session)
        service = await auth.create_user(
            owner_context.user,
            username="future-ai",
            role=UserRole.service,
        )
        assert service.service_token is not None
        service_model = await session.get(UserModel, service.id)
        assert service_model is not None
        assert service_model.service_owner_id == owner_model.id
        entry_key = generate_entry_key()
        cleartext = Password(
            password_name="shared",
            password_value="secret",
            url="https://example.com",
            tags=["production"],
        )
        payload = cleartext.model_dump(exclude={"favorite"})
        payload.update(password_history=[], backed_up=False)

        def encoded(value: bytes) -> str:
            return base64.urlsafe_b64encode(value).decode().rstrip("=")

        encrypted = EncryptedPasswordCRUD(session)
        created = await encrypted.create(
            owner_context,
            encrypted_payload=encrypt(entry_key, json.dumps(payload).encode()).decode(),
            wrapped_key=encoded(wrap_entry_key(owner_model.public_key, entry_key)),
            encrypted_preferences=encrypt(entry_key, b'{"favorite":false}').decode(),
        )
        service_wrapped_key = encoded(
            wrap_entry_key(service_model.public_key, entry_key)
        )
        await encrypted.share(
            owner_context,
            created.id,
            service.id,
            permission=SharePermission.read,
            wrapped_key=service_wrapped_key,
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
                "create_entry",
                "relinquish_entry",
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
                await EncryptedPasswordCRUD(session).share(
                    owner_context,
                    entry_id,
                    service.id,
                    permission=SharePermission.write,
                    wrapped_key=service_wrapped_key,
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
                            "changes": {
                                "password_value": "changed",
                                "favorite": True,
                            },
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
            assert reread.json()["result"]["structuredContent"]["favorite"] is True

            created_by_service = await _post_mcp(
                client,
                token,
                {
                    "jsonrpc": "2.0",
                    "id": 9,
                    "method": "tools/call",
                    "params": {
                        "name": "create_entry",
                        "arguments": {
                            "entry": {
                                "password_name": "created-by-agent",
                                "password_value": "generated-secret",
                                "url": "https://created.example",
                            }
                        },
                    },
                },
                protocol_version,
            )
            created_content = created_by_service.json()["result"]["structuredContent"]
            assert created_content["owner_username"] == "owner"
            assert created_content["access"] == "write"
            created_id = created_content["id"]

            async with maker() as session:
                owner_grant = await session.get(
                    PasswordAccessModel, (created_id, owner_model.id)
                )
                service_grant = await session.get(
                    PasswordAccessModel, (created_id, service.id)
                )
                assert owner_grant is not None
                assert owner_grant.permission == "owner"
                assert service_grant is not None
                assert service_grant.permission == "write"

            listed_after_create = await _post_mcp(
                client,
                token,
                {
                    "jsonrpc": "2.0",
                    "id": 10,
                    "method": "tools/call",
                    "params": {"name": "list_entries", "arguments": {}},
                },
                protocol_version,
            )
            listed_entries = listed_after_create.json()["result"]["structuredContent"][
                "result"
            ]
            assert {entry["name"] for entry in listed_entries} == {
                "shared",
                "created-by-agent",
            }

            relinquished = await _post_mcp(
                client,
                token,
                {
                    "jsonrpc": "2.0",
                    "id": 11,
                    "method": "tools/call",
                    "params": {
                        "name": "relinquish_entry",
                        "arguments": {"entry_id": created_id},
                    },
                },
                protocol_version,
            )
            assert relinquished.json()["result"]["structuredContent"] == {
                "entry_id": created_id,
                "relinquished": True,
            }
            async with maker() as session:
                assert (
                    await session.get(PasswordAccessModel, (created_id, owner_model.id))
                ) is not None
                assert (
                    await session.get(PasswordAccessModel, (created_id, service.id))
                ) is None

            listed_after_relinquish = await _post_mcp(
                client,
                token,
                {
                    "jsonrpc": "2.0",
                    "id": 12,
                    "method": "tools/call",
                    "params": {"name": "list_entries", "arguments": {}},
                },
                protocol_version,
            )
            assert [
                entry["name"]
                for entry in listed_after_relinquish.json()["result"][
                    "structuredContent"
                ]["result"]
            ] == ["shared"]

            async with maker() as session:
                await AuthCRUD(session).update_user(
                    owner_context.user, service.id, active=False
                )
                await session.commit()

            revoked = await _post_mcp(
                client,
                token,
                {"jsonrpc": "2.0", "id": 13, "method": "tools/list"},
                protocol_version,
            )
            assert revoked.status_code == 401

    await engine.dispose()
