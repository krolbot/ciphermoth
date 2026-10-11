import base64
import hashlib
import hmac
import io
import json
import struct
from pathlib import Path

import httpx
import pytest
import pyzipper
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

import helpers
from schemas import MasterPassword
from tests.support import auth, create_vault
from tests.tools import generate_vectors

VECTORS = Path(__file__).resolve().parents[2] / "testdata" / "vectors"


def load(name: str) -> dict:
    data = json.loads((VECTORS / name).read_text(encoding="utf-8"))
    assert data["format"] == "ciphermoth-test-vectors/1"
    return data


def _ids(vectors: list[dict]) -> list[str]:
    return [v.get("note") or v.get("source", "") for v in vectors]


def reference_decrypt(key: str, token: bytes) -> bytes:
    raw_key = base64.urlsafe_b64decode(key)
    data = base64.urlsafe_b64decode(token)
    body, mac = data[:-32], data[-32:]
    expected = hmac.new(raw_key[:16], body, hashlib.sha256).digest()
    assert hmac.compare_digest(mac, expected)
    assert body[0] == 0x80
    iv, ciphertext = body[9:25], body[25:]
    decryptor = Cipher(algorithms.AES(raw_key[16:]), modes.CBC(iv)).decryptor()
    padded = decryptor.update(ciphertext) + decryptor.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    return unpadder.update(padded) + unpadder.finalize()


ARGON2 = load("argon2id.json")


@pytest.mark.parametrize("vector", ARGON2["vectors"], ids=_ids(ARGON2["vectors"]))
def test_argon2id_key_derivation(vector: dict) -> None:
    assert vector["password"].encode().hex() == vector["password_utf8_hex"]
    key = helpers.generate_key_derivation(
        bytes.fromhex(vector["salt_hex"]), vector["password"]
    )
    assert key.decode() == vector["key"]


def test_argon2id_applies_no_unicode_normalization() -> None:
    keys = {v["note"].split(" ")[0]: v["key"] for v in ARGON2["vectors"]}
    assert keys["NFC"] != keys["NFD"]


@pytest.mark.parametrize("case", ARGON2["api_input"]["cases"])
def test_master_password_reaching_the_kdf(case: dict) -> None:
    submitted = MasterPassword.model_validate({"master_password": case["submitted"]})
    assert submitted.master_password == case["kdf_input"]


FERNET = load("fernet.json")


@pytest.mark.parametrize("vector", FERNET["vectors"], ids=_ids(FERNET["vectors"]))
def test_fernet_tokens_decrypt(vector: dict) -> None:
    token = vector["token"].encode()
    expected = bytes.fromhex(vector["plaintext_hex"])
    assert helpers.decrypt_bytes(vector["key"], token) == expected
    assert reference_decrypt(vector["key"], token) == expected
    if vector["plaintext"] is not None:
        assert helpers.decrypt(vector["key"], token) == vector["plaintext"]
        assert helpers.decrypt_optional(vector["key"], token) == vector["plaintext"]
    data = base64.urlsafe_b64decode(token)
    assert data[0] == 0x80
    assert struct.unpack(">Q", data[1:9])[0] == vector["timestamp"]
    assert data[9:25].hex() == vector["iv_hex"]


@pytest.mark.parametrize("vector", FERNET["invalid"], ids=_ids(FERNET["invalid"]))
def test_invalid_fernet_tokens_are_refused(vector: dict) -> None:
    assert helpers.decrypt(vector["key"], vector["token"].encode()) is None
    assert helpers.decrypt_bytes(vector["key"], vector["token"].encode()) is None


@pytest.mark.parametrize(
    "plaintext", [b"", b"x", "ключ 🦋".encode(), bytes(range(256)) * 3]
)
def test_new_tokens_follow_the_specification(plaintext: bytes) -> None:
    key = FERNET["vectors"][0]["key"]
    token = helpers.encrypt(key, plaintext)
    assert reference_decrypt(key, token) == plaintext
    assert helpers.encrypt(key, plaintext) != token


KEY_CHECK = load("key_check.json")


def test_key_check_token_verifies() -> None:
    salt = bytes.fromhex(KEY_CHECK["salt_hex"])
    key = helpers.generate_key_derivation(salt, KEY_CHECK["password"]).decode()
    assert key == KEY_CHECK["key"]
    token = KEY_CHECK["token"].encode()
    assert helpers.verify_key_check(key, token, salt)
    assert helpers.verify_key_check(key.encode(), token, salt)
    assert not helpers.verify_key_check(key, token, bytes(16))
    fresh = helpers.create_key_check(key, salt)
    assert reference_decrypt(key, fresh) == b"ciphermoth-key-check-v1:" + salt


@pytest.mark.parametrize(
    "rejected", KEY_CHECK["rejected_keys"], ids=_ids(KEY_CHECK["rejected_keys"])
)
def test_key_check_rejects_non_canonical_and_partial_keys(rejected: dict) -> None:
    assert not helpers.verify_key_check(
        rejected["key"],
        KEY_CHECK["token"].encode(),
        bytes.fromhex(KEY_CHECK["salt_hex"]),
    )


BCRYPT = load("bcrypt.json")


@pytest.mark.parametrize("vector", BCRYPT["vectors"], ids=_ids(BCRYPT["vectors"]))
def test_bcrypt_hashes_verify(vector: dict) -> None:
    assert helpers.verify_master_password(vector["password"], vector["hash"])


@pytest.mark.parametrize("vector", BCRYPT["mismatches"], ids=_ids(BCRYPT["mismatches"]))
def test_bcrypt_mismatches_do_not_verify(vector: dict) -> None:
    assert not helpers.verify_master_password(vector["password"], vector["hash"])


def test_new_bcrypt_hashes_use_the_documented_scheme() -> None:
    hashed = helpers.hash_master_password("Moth-Test-Vault-2026!")
    assert hashed.startswith("$2b$12$")
    assert helpers.verify_master_password("Moth-Test-Vault-2026!", hashed)


TOTP = load("totp.json")


@pytest.mark.parametrize("vector", TOTP["vectors"])
def test_totp(vector: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(helpers.time, "time", lambda: float(vector["time"]))
    code = helpers.generate_totp(
        vector["secret"], digits=vector["digits"], period=vector["period"]
    )
    assert code == vector["code"]


BACKUP = load("backup_zip.json")


def test_frozen_backup_zip_opens_with_its_password() -> None:
    archive = (VECTORS / BACKUP["file"]).read_bytes()
    with pyzipper.AESZipFile(io.BytesIO(archive)) as zf:
        assert zf.namelist() == [BACKUP["member"]]
        zf.setpassword(BACKUP["password"].encode())
        assert json.loads(zf.read(BACKUP["member"])) == BACKUP["json"]
    with (
        pytest.raises(RuntimeError),
        pyzipper.AESZipFile(io.BytesIO(archive)) as zf,
    ):
        zf.setpassword(b"wrong password")
        zf.read(BACKUP["member"])


async def test_frozen_backup_zip_restores_into_a_new_vault(
    client: httpx.AsyncClient,
) -> None:
    key = await create_vault(client, BACKUP["password"])
    resp = await client.post(
        "/passwords/import",
        data={"master_password": BACKUP["password"]},
        files={"file": ("b.zip", (VECTORS / BACKUP["file"]).read_bytes(), "x/y")},
        headers=auth(key),
    )
    assert resp.status_code == 200, resp.text
    restored = {
        p["password_name"]: p
        for p in (await client.get("/passwords", headers=auth(key))).json()
    }
    for item in BACKUP["json"]["passwords"]:
        got = restored[item["name"]]
        assert got["password_value"] == item["value"]
        for field in ("kind", "username", "url", "totp_secret", "description"):
            assert got[field] == item[field]
        assert got["tags"] == item["tags"]
        assert got["custom_fields"] == item["custom_fields"]
        assert got["folder"] == item["folder"]
        assert got["favorite"] == item["favorite"]


@pytest.mark.parametrize(
    ("name", "build"),
    [
        ("argon2id.json", generate_vectors.argon2id_vectors),
        ("fernet.json", generate_vectors.fernet_vectors),
        ("key_check.json", generate_vectors.key_check_vectors),
        ("bcrypt.json", generate_vectors.bcrypt_vectors),
    ],
)
def test_the_reference_construction_still_reproduces_the_frozen_files(
    name: str, build
) -> None:
    assert json.loads(json.dumps(build(), ensure_ascii=False)) == load(name)
