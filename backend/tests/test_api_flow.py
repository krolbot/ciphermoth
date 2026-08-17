import base64
import hashlib
from collections.abc import AsyncGenerator

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api.endpoints.deps import get_session
from crud.auth import _rekey_message
from helpers import (
    create_user_keypair,
    decrypt_user_private_key,
    encrypt,
    encrypt_user_private_key,
    generate_entry_key,
    generate_key_derivation,
    wrap_entry_key,
)
from main import app
from models import BaseModel, InstanceStateModel


def encoded(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def key_material(
    password: str, salt: bytes
) -> tuple[dict[str, str], Ed25519PrivateKey]:
    key = generate_key_derivation(salt, password)
    public_key, encrypted_private_key = create_user_keypair(key)
    auth_private = Ed25519PrivateKey.generate()
    return (
        {
            "salt": encoded(salt),
            "public_key": encoded(public_key),
            "encrypted_private_key": encrypted_private_key.decode(),
            "auth_public_key": encoded(
                auth_private.public_key().public_bytes(
                    serialization.Encoding.Raw, serialization.PublicFormat.Raw
                )
            ),
            "encrypted_auth_private_key": encrypt(
                key,
                auth_private.private_bytes(
                    serialization.Encoding.DER,
                    serialization.PrivateFormat.PKCS8,
                    serialization.NoEncryption(),
                ),
            ).decode(),
        },
        auth_private,
    )


@pytest.mark.asyncio
async def test_multi_user_ciphertext_sharing_http_flow() -> None:
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
    owner_password = "correct horse battery staple"
    member_password = "temporary member password 123!"
    try:
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            preflight = await client.options(
                "/api/users",
                headers={
                    "Origin": "http://localhost:3000",
                    "Access-Control-Request-Method": "GET",
                    "Access-Control-Request-Headers": "authorization",
                },
            )
            assert preflight.status_code == 200

            owner_keys, _ = key_material(owner_password, b"0123456789abcdef")
            bootstrap = await client.post(
                "/api/auth/bootstrap",
                json={
                    "username": "owner",
                    **owner_keys,
                },
            )
            assert bootstrap.status_code == 200
            bootstrap_data = bootstrap.json()
            assert "key_derivation" not in bootstrap_data
            owner_headers = {"Authorization": f"Bearer {bootstrap_data['token']}"}

            member_keys, member_auth_private = key_material(
                member_password, b"fedcba9876543210"
            )
            member = await client.post(
                "/api/users",
                headers=owner_headers,
                json={
                    "username": "member",
                    "role": "member",
                    **member_keys,
                },
            )
            assert member.status_code == 200
            member_id = member.json()["id"]
            entry_key = generate_entry_key()
            owner_ciphertext = encrypt(entry_key, b"owner ciphertext")
            changed_ciphertext = encrypt(entry_key, b"changed ciphertext")
            owner_public_key = base64.urlsafe_b64decode(
                bootstrap_data["public_key"] + "=="
            )
            member_public_key = base64.urlsafe_b64decode(
                member_keys["public_key"] + "=="
            )

            created = await client.post(
                "/api/passwords",
                headers=owner_headers,
                json={
                    "encrypted_payload": owner_ciphertext.decode(),
                    "wrapped_key": encoded(wrap_entry_key(owner_public_key, entry_key)),
                    "encrypted_preferences": encrypt(
                        entry_key, b"owner preferences"
                    ).decode(),
                },
            )
            assert created.status_code == 200
            entry_id = created.json()["id"]

            shared = await client.put(
                f"/api/passwords/{entry_id}/shares/{member_id}",
                headers=owner_headers,
                json={
                    "permission": "read",
                    "wrapped_key": encoded(
                        wrap_entry_key(member_public_key, entry_key)
                    ),
                },
            )
            assert shared.status_code == 200

            member_challenge = await client.post(
                "/api/auth/challenge", json={"username": "member"}
            )
            assert member_challenge.status_code == 200
            member_challenge_data = member_challenge.json()
            member_login = await client.post(
                "/api/auth/login",
                json={
                    "challenge": member_challenge_data["challenge"],
                    "signature": encoded(
                        member_auth_private.sign(
                            base64.urlsafe_b64decode(
                                member_challenge_data["nonce"] + "=="
                            )
                        )
                    ),
                },
            )
            assert member_login.status_code == 200
            private_key = decrypt_user_private_key(
                generate_key_derivation(b"fedcba9876543210", member_password),
                member_keys["encrypted_private_key"].encode(),
            )
            permanent_password = "permanent member password 456!"
            permanent_salt = b"0011223344556677"
            permanent_key = generate_key_derivation(permanent_salt, permanent_password)
            permanent_private_key = encrypt_user_private_key(permanent_key, private_key)
            permanent_auth_private_key = encrypt(
                permanent_key,
                member_auth_private.private_bytes(
                    serialization.Encoding.DER,
                    serialization.PrivateFormat.PKCS8,
                    serialization.NoEncryption(),
                ),
            )
            session_hash = hashlib.sha256(
                member_login.json()["token"].encode()
            ).hexdigest()
            changed_password = await client.put(
                "/api/auth/password",
                headers={"Authorization": f"Bearer {member_login.json()['token']}"},
                json={
                    "new_salt": encoded(permanent_salt),
                    "encrypted_private_key": permanent_private_key.decode(),
                    "encrypted_auth_private_key": permanent_auth_private_key.decode(),
                    "proof": encoded(
                        member_auth_private.sign(
                            _rekey_message(
                                session_hash,
                                permanent_salt,
                                permanent_private_key,
                                permanent_auth_private_key,
                            )
                        )
                    ),
                },
            )
            assert changed_password.status_code == 200
            member_headers = {
                "Authorization": f"Bearer {changed_password.json()['token']}"
            }
            fetched = await client.get(
                f"/api/passwords/{entry_id}", headers=member_headers
            )
            assert fetched.status_code == 200
            assert fetched.json()["encrypted_payload"] == owner_ciphertext.decode()
            assert fetched.json()["access"] == "read"

            denied = await client.put(
                f"/api/passwords/{entry_id}",
                headers=member_headers,
                json={"encrypted_payload": changed_ciphertext.decode()},
            )
            assert denied.status_code == 403

            upgraded = await client.put(
                f"/api/passwords/{entry_id}/shares/{member_id}",
                headers=owner_headers,
                json={
                    "permission": "write",
                    "wrapped_key": encoded(
                        wrap_entry_key(member_public_key, entry_key)
                    ),
                },
            )
            assert upgraded.status_code == 200
            changed = await client.put(
                f"/api/passwords/{entry_id}",
                headers=member_headers,
                json={"encrypted_payload": changed_ciphertext.decode()},
            )
            assert changed.status_code == 200
            assert changed.json()["encrypted_payload"] == changed_ciphertext.decode()
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()
