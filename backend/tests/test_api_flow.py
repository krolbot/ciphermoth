from collections.abc import AsyncGenerator

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api.endpoints.deps import get_session
from main import app
from models import BaseModel, InstanceStateModel


@pytest.mark.asyncio
async def test_multi_user_sharing_http_flow() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(BaseModel.metadata.create_all)
    async with maker() as session:
        session.add(InstanceStateModel(id=1))
        await session.commit()

    async def session_override() -> AsyncGenerator[AsyncSession]:
        async with maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_session] = session_override
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            preflight = await client.options(
                "/api/users",
                headers={
                    "Origin": "http://localhost:3000",
                    "Access-Control-Request-Method": "GET",
                    "Access-Control-Request-Headers": (
                        "authorization,x-ciphermoth-key-derivation"
                    ),
                },
            )
            assert preflight.status_code == 200
            bootstrap = await client.post(
                "/api/auth/bootstrap",
                json={
                    "username": "owner",
                    "master_password": "correct horse battery staple",
                },
            )
            assert bootstrap.status_code == 200
            owner_auth = bootstrap.json()
            owner_headers = {
                "authorization": f"Bearer {owner_auth['token']}",
                "x-ciphermoth-key-derivation": owner_auth["key_derivation"],
            }

            member = await client.post(
                "/api/users",
                headers=owner_headers,
                json={
                    "username": "alice",
                    "temporary_password": "temporary member password 1",
                    "role": "member",
                },
            )
            assert member.status_code == 200
            member_id = member.json()["id"]

            member_login = await client.post(
                "/api/auth/login",
                json={
                    "username": "alice",
                    "master_password": "temporary member password 1",
                },
            )
            assert member_login.status_code == 200
            member_auth = member_login.json()
            temporary_headers = {
                "authorization": f"Bearer {member_auth['token']}",
                "x-ciphermoth-key-derivation": member_auth["key_derivation"],
            }
            blocked = await client.get("/api/passwords", headers=temporary_headers)
            assert blocked.status_code == 403

            changed = await client.put(
                "/api/auth/password",
                headers=temporary_headers,
                json={
                    "current_password": "temporary member password 1",
                    "new_password": "permanent member password 2",
                },
            )
            assert changed.status_code == 200
            member_auth = changed.json()
            member_headers = {
                "authorization": f"Bearer {member_auth['token']}",
                "x-ciphermoth-key-derivation": member_auth["key_derivation"],
            }

            created = await client.post(
                "/api/passwords",
                headers=owner_headers,
                json={"password_name": "shared", "password_value": "secret"},
            )
            assert created.status_code == 200
            password_id = created.json()["id"]

            grant = await client.put(
                f"/api/passwords/{password_id}/shares/{member_id}",
                headers=owner_headers,
                json={"permission": "read"},
            )
            assert grant.status_code == 200
            assert grant.json()["permission"] == "read"

            shared = await client.get(
                f"/api/passwords/{password_id}", headers=member_headers
            )
            assert shared.status_code == 200
            assert shared.json()["password_value"] == "secret"
            assert shared.json()["access"] == "read"

            denied = await client.put(
                f"/api/passwords/{password_id}",
                headers=member_headers,
                json={"password_name": "shared", "password_value": "changed"},
            )
            assert denied.status_code == 403
            assert (
                await client.get("/api/auth/me", headers=member_headers)
            ).status_code == 200
            assert (
                await client.post("/api/auth/logout", headers=member_headers)
            ).status_code == 200
            expired = await client.get("/api/auth/me", headers=member_headers)
            assert expired.status_code == 401
            assert expired.headers["www-authenticate"] == "Bearer"
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()
