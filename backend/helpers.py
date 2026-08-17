import base64
import hashlib
import hmac
import io
import json
import os
import struct
import time
from datetime import UTC, datetime

import pyzipper
from cryptography.exceptions import InvalidTag
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

_ARGON2_MEMORY_COST = 65536
_ARGON2_ITERATIONS = 3
_ARGON2_LANES = 4
_ARGON2_LENGTH = 32
_ENTRY_KEY_WRAP_INFO = b"ciphermoth-entry-key-v1"
_ENTRY_KEY_WRAP_VERSION = 1


def generate_key_derivation(salt: bytes, master_password: str) -> bytes:
    kdf = Argon2id(
        salt=salt,
        length=_ARGON2_LENGTH,
        iterations=_ARGON2_ITERATIONS,
        lanes=_ARGON2_LANES,
        memory_cost=_ARGON2_MEMORY_COST,
    )
    return base64.urlsafe_b64encode(kdf.derive(master_password.encode()))


def encrypt(key: bytes | str, value: bytes) -> bytes:
    return Fernet(key).encrypt(value)


def decrypt(key: bytes | str, encrypted_value: bytes) -> str | None:
    try:
        return Fernet(key).decrypt(encrypted_value).decode()
    except InvalidToken:
        return None


def decrypt_bytes(key: bytes | str, encrypted_value: bytes) -> bytes | None:
    try:
        return Fernet(key).decrypt(encrypted_value)
    except InvalidToken:
        return None


def encrypt_optional(key: bytes | str, value: str | None) -> bytes | None:
    if value is None:
        return None
    return encrypt(key, value.encode())


def decrypt_optional(key: bytes | str, encrypted_value: bytes | None) -> str | None:
    if encrypted_value is None:
        return None
    return decrypt(key, encrypted_value)


def generate_entry_key() -> bytes:
    return Fernet.generate_key()


def create_user_keypair(user_key: bytes | str) -> tuple[bytes, bytes]:
    private_key = X25519PrivateKey.generate()
    private_bytes = private_key.private_bytes_raw()
    public_bytes = private_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    return public_bytes, encrypt(user_key, private_bytes)


def encrypt_user_private_key(user_key: bytes | str, private_key: bytes) -> bytes:
    return encrypt(user_key, private_key)


def decrypt_user_private_key(
    user_key: bytes | str, encrypted_private_key: bytes
) -> bytes:
    private_key = decrypt_bytes(user_key, encrypted_private_key)
    if private_key is None:
        raise ValueError("Could not decrypt user private key.")
    return private_key


def _entry_key_wrap_key(shared_secret: bytes, context: bytes) -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=_ENTRY_KEY_WRAP_INFO + b":" + context,
    ).derive(shared_secret)


def wrap_entry_key(public_key: bytes, entry_key: bytes, context: bytes = b"") -> bytes:
    ephemeral = X25519PrivateKey.generate()
    shared_secret = ephemeral.exchange(X25519PublicKey.from_public_bytes(public_key))
    nonce = os.urandom(12)
    authenticated_context = _ENTRY_KEY_WRAP_INFO + b":" + context
    encrypted = AESGCM(_entry_key_wrap_key(shared_secret, context)).encrypt(
        nonce, entry_key, authenticated_context
    )
    ephemeral_public = ephemeral.public_key().public_bytes_raw()
    return bytes([_ENTRY_KEY_WRAP_VERSION]) + ephemeral_public + nonce + encrypted


def unwrap_entry_key(
    private_key: bytes, wrapped_key: bytes, context: bytes = b""
) -> bytes:
    try:
        if len(wrapped_key) < 62 or wrapped_key[0] != _ENTRY_KEY_WRAP_VERSION:
            raise ValueError
        ephemeral_public = X25519PublicKey.from_public_bytes(wrapped_key[1:33])
        nonce = wrapped_key[33:45]
        encrypted = wrapped_key[45:]
        shared_secret = X25519PrivateKey.from_private_bytes(private_key).exchange(
            ephemeral_public
        )
        return AESGCM(_entry_key_wrap_key(shared_secret, context)).decrypt(
            nonce, encrypted, _ENTRY_KEY_WRAP_INFO + b":" + context
        )
    except (ValueError, InvalidTag) as exc:
        raise ValueError("Could not decrypt entry key.") from exc


def generate_totp(secret: str, *, digits: int = 6, period: int = 30) -> str:
    """
    Return the current TOTP code for a base32 secret (RFC 6238, HMAC-SHA1).

    Used by the CLI so `password get` can show the live code. The web UI has its
    own Web Crypto implementation; both stay small and dependency-free so the
    two-factor path is easy to audit.
    """
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    counter = int(time.time()) // period
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(code % (10**digits)).zfill(digits)


def create_encrypted_zip(entries: list[dict[str, object]], password: str) -> bytes:
    payload = json.dumps(
        {"exported_at": datetime.now(UTC).isoformat(), "passwords": entries},
        indent=2,
        ensure_ascii=False,
    ).encode("utf-8")

    buf = io.BytesIO()
    with pyzipper.AESZipFile(
        buf, "w", compression=pyzipper.ZIP_DEFLATED, encryption=pyzipper.WZ_AES
    ) as zf:
        zf.setpassword(password.encode())
        zf.writestr("ciphermoth_backup.json", payload)
    return buf.getvalue()
