"""
Write the frozen cryptographic test vectors in testdata/vectors.

The vectors are generated once and committed; tests only ever read them. Every
expected value is computed from the primitive libraries following the
construction documented in testdata/vectors/README.md, not from helpers.py,
so the tests check the application against an independent derivation.

Run from backend/: uv run python -m tests.tools.generate_vectors [--force]
"""

import argparse
import base64
import hashlib
import hmac
import io
import json
import struct
import sys
import unicodedata
from pathlib import Path

import bcrypt
import pyzipper
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id

OUT = Path(__file__).resolve().parents[3] / "testdata" / "vectors"
FORMAT = "ciphermoth-test-vectors/1"


def argon2id_key(password: str, salt: bytes) -> str:
    raw = Argon2id(
        salt=salt, length=32, iterations=3, lanes=4, memory_cost=65536
    ).derive(password.encode("utf-8"))
    return base64.urlsafe_b64encode(raw).decode()


def fernet_token(key: str, plaintext: bytes, iv: bytes, timestamp: int) -> str:
    raw_key = base64.urlsafe_b64decode(key)
    signing_key, encryption_key = raw_key[:16], raw_key[16:]
    padder = padding.PKCS7(128).padder()
    padded = padder.update(plaintext) + padder.finalize()
    encryptor = Cipher(algorithms.AES(encryption_key), modes.CBC(iv)).encryptor()
    ciphertext = encryptor.update(padded) + encryptor.finalize()
    body = b"\x80" + struct.pack(">Q", timestamp) + iv + ciphertext
    mac = hmac.new(signing_key, body, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(body + mac).decode()


def bcrypt_input(password: str) -> bytes:
    return base64.b64encode(hashlib.sha256(password.encode("utf-8")).digest())


def doc(name: str, description: str, **sections: object) -> dict:
    return {"format": FORMAT, "name": name, "description": description, **sections}


ARGON2_PASSWORDS = [
    ("Moth-Test-Vault-2026!", "00" * 16, "ASCII"),
    ("correct horse battery staple", "ff" * 16, "spaces inside"),
    ("Mölle-Stern-2026", "a1b2c3d4e5f60718293a4b5c6d7e8f90", "NFC"),
    (
        unicodedata.normalize("NFD", "Mölle-Stern-2026"),
        "a1b2c3d4e5f60718293a4b5c6d7e8f90",
        "NFD form of the previous vector: no Unicode normalization, different key",
    ),
    ("ключ-вольта-2026", "0f1e2d3c4b5a69788796a5b4c3d2e1f0", "Cyrillic"),
    ("パスワード2026!", "13579bdf02468ace13579bdf02468ace", "Japanese"),
    ("🦋 moth 🦋 2026", "deadbeefdeadbeefdeadbeefdeadbeef", "emoji, 4-byte UTF-8"),
    ("סיסמה-2026-ok", "0123456789abcdeffedcba9876543210", "right-to-left"),
    ("two  spaces\tand\ttabs 2026", "55" * 16, "inner whitespace is kept"),
    ("x" * 1023 + "!", "77" * 16, "1024 characters, the API maximum"),
]

STRIP_CASES = [
    ("  Moth-Test-Vault-2026!  ", "Moth-Test-Vault-2026!"),
    ("\tMoth-Test-Vault-2026!\n", "Moth-Test-Vault-2026!"),
    (" Moth-Test-Vault-2026!　", "Moth-Test-Vault-2026!"),
    ("​Moth-Test-Vault-2026!", "​Moth-Test-Vault-2026!"),
    ("\x1cMoth-Test-Vault-2026!", "\x1cMoth-Test-Vault-2026!"),
    ("Moth Test Vault 2026!", "Moth Test Vault 2026!"),
]

FERNET_CASES = [
    ("", "empty plaintext"),
    ("s3cret-Value!", "ASCII password"),
    ("  line one\n\tline two\n\n", "note with surrounding whitespace"),
    ("ключ 🦋 パス", "multi-byte UTF-8"),
    ("x" * 16, "exactly one AES block, padded with a full block"),
    ('["dev","ops"]', "tags JSON as stored"),
    (
        '[{"label": "PIN", "value": "1234", "hidden": true}]',
        "custom fields JSON as stored",
    ),
    (
        '[{"value": "old", "changed_at": "2026-01-01T00:00:00+00:00"}]',
        "password history JSON as stored",
    ),
]


def argon2id_vectors() -> dict:
    vectors = [
        {
            "password": password,
            "password_utf8_hex": password.encode().hex(),
            "salt_hex": salt,
            "key": argon2id_key(password, bytes.fromhex(salt)),
            "note": note,
        }
        for password, salt, note in ARGON2_PASSWORDS
    ]
    return doc(
        "argon2id",
        "Vault key derivation. key = base64url(Argon2id(password_utf8, salt, "
        "m=65536 KiB, t=3, p=4, length=32, version 0x13, no secret, no "
        "associated data)), 44 characters with '=' padding. The result is used "
        "directly as a Fernet key. No Unicode normalization is applied.",
        parameters={
            "memory_cost_kib": 65536,
            "iterations": 3,
            "lanes": 4,
            "length": 32,
            "salt_length": 16,
            "version": 19,
        },
        vectors=vectors,
        api_input={
            "description": "The API strips the master password with pydantic's "
            "str_strip_whitespace (Unicode White_Space) before hashing and "
            "derivation. Characters such as U+200B or U+001C are not stripped, "
            "unlike Python's str.strip(). kdf_input is what reaches Argon2id "
            "and bcrypt.",
            "cases": [
                {"submitted": submitted, "kdf_input": kdf_input}
                for submitted, kdf_input in STRIP_CASES
            ],
        },
    )


def fernet_vectors() -> dict:
    key = argon2id_key("Moth-Test-Vault-2026!", bytes(16))
    vectors = []
    for index, (plaintext, note) in enumerate(FERNET_CASES):
        iv = bytes((index * 16 + n) % 256 for n in range(16))
        timestamp = 1_760_000_000 + index
        data = plaintext.encode("utf-8")
        vectors.append(
            {
                "key": key,
                "plaintext": plaintext,
                "plaintext_hex": data.hex(),
                "iv_hex": iv.hex(),
                "timestamp": timestamp,
                "token": fernet_token(key, data, iv, timestamp),
                "note": note,
            }
        )
    binary = bytes(range(256)) + b"\xff\xfe\x00\x80"
    vectors.append(
        {
            "key": key,
            "plaintext": None,
            "plaintext_hex": binary.hex(),
            "iv_hex": "f0" * 16,
            "timestamp": 1_760_000_100,
            "token": fernet_token(key, binary, b"\xf0" * 16, 1_760_000_100),
            "note": "attachment content: arbitrary bytes, not UTF-8",
        }
    )
    good = str(vectors[1]["token"])
    raw = bytearray(base64.urlsafe_b64decode(good))
    flipped_ciphertext = bytes(raw[:30]) + bytes([raw[30] ^ 1]) + bytes(raw[31:])
    flipped_mac = bytes(raw[:-1]) + bytes([raw[-1] ^ 1])
    wrong_version = b"\x81" + bytes(raw[1:])
    invalid = [
        {"key": key, "token": good[:-4], "note": "truncated"},
        {
            "key": key,
            "token": base64.urlsafe_b64encode(flipped_ciphertext).decode(),
            "note": "one ciphertext bit flipped",
        },
        {
            "key": key,
            "token": base64.urlsafe_b64encode(flipped_mac).decode(),
            "note": "one MAC bit flipped",
        },
        {
            "key": key,
            "token": base64.urlsafe_b64encode(wrong_version).decode(),
            "note": "version byte 0x81",
        },
        {
            "key": argon2id_key("Moth-Test-Vault-2026?", bytes(16)),
            "token": good,
            "note": "key derived from a different password",
        },
        {"key": key, "token": "", "note": "empty token"},
    ]
    return doc(
        "fernet",
        "Every encrypted column (and the key check) is a Fernet token, spec "
        "version 0x80: base64url(0x80 || timestamp u64 BE || IV(16) || "
        "AES-128-CBC(key[16:32], PKCS7(plaintext)) || HMAC-SHA256(key[0:16], "
        "all previous bytes)), stored as the ASCII bytes of that string. Text "
        "columns hold UTF-8; JSON columns hold UTF-8 JSON; attachment content "
        "holds raw bytes. Tokens never expire (no TTL is checked).",
        vectors=vectors,
        invalid=invalid,
    )


def key_check_vectors() -> dict:
    salt = bytes.fromhex("a1b2c3d4e5f60718293a4b5c6d7e8f90")
    password = "Mölle-Stern-2026"
    key = argon2id_key(password, salt)
    iv = bytes(range(32, 48))
    token = fernet_token(key, b"ciphermoth-key-check-v1:" + salt, iv, 1_760_000_000)
    raw = base64.urlsafe_b64decode(key)
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    low_bit_variant = key[:42] + alphabet[alphabet.index(key[42]) ^ 1] + "="
    rejected = [
        {"key": key.rstrip("="), "note": "padding removed"},
        {"key": key + "\n", "note": "trailing newline"},
        {"key": key.replace("-", "+").replace("_", "/"), "note": "standard alphabet"},
        {"key": low_bit_variant, "note": "unused low bits of the last character"},
        {
            "key": base64.urlsafe_b64encode(raw[:16] + bytes(16)).decode(),
            "note": "right signing half, wrong encryption half",
        },
        {
            "key": base64.urlsafe_b64encode(bytes(16) + raw[16:]).decode(),
            "note": "right encryption half, wrong signing half",
        },
    ]
    return doc(
        "key_check",
        "master_password.key_check = Fernet(key).encrypt('ciphermoth-key-check-v1:' "
        "|| salt). A key is accepted only if it is the canonical 44-character "
        "base64url encoding (re-encoding the decoded bytes gives the same "
        "string) and the token decrypts to exactly that plaintext for the "
        "vault's current salt.",
        password=password,
        salt_hex=salt.hex(),
        key=key,
        iv_hex=iv.hex(),
        timestamp=1_760_000_000,
        token=token,
        rejected_keys=[r for r in rejected if r["key"] != key],
    )


def bcrypt_vectors() -> dict:
    cases = [
        ("Moth-Test-Vault-2026!", 12, "production cost"),
        ("Mölle-Stern-2026", 4, "non-ASCII"),
        ("🦋 moth 🦋 2026", 4, "emoji"),
        ("p" * 80 + "-tail-A", 4, "longer than bcrypt's 72-byte limit"),
        ("x" * 1023 + "!", 4, "1024 characters"),
    ]
    salts = [
        b"OGyGkYrUzOlOtUhcm7c8We",
        b"WSo4z8ANLkVRgD1AJxsIbe",
        b"1fC2ZAfZpi8u6/1Y8B5b0O",
        b"jy4W26X1lYTxkSy2KHl5fe",
        b"ZiOmNWq7yh8xZt0X/56ZUe",
    ]
    vectors = []
    for (password, cost, note), salt in zip(cases, salts, strict=True):
        prefix = f"$2b${cost:02d}$".encode() + salt
        hashed = bcrypt.hashpw(bcrypt_input(password), prefix).decode()
        vectors.append({"password": password, "hash": hashed, "note": note})
    long_hash = vectors[3]["hash"]
    mismatches = [
        {
            "password": "p" * 80 + "-tail-B",
            "hash": long_hash,
            "note": "same first 72 bytes: must not verify thanks to the SHA-256 "
            "pre-hash",
        },
        {
            "password": "Moth-Test-Vault-2026?",
            "hash": vectors[0]["hash"],
            "note": "wrong password",
        },
        {
            "password": unicodedata.normalize("NFD", "Mölle-Stern-2026"),
            "hash": vectors[1]["hash"],
            "note": "NFD form of the NFC password",
        },
        {
            "password": "Moth-Test-Vault-2026!",
            "hash": bcrypt.hashpw(
                b"Moth-Test-Vault-2026!", b"$2b$04$" + salts[0]
            ).decode(),
            "note": "plain bcrypt without the pre-hash, as before v0.3.0: unsupported",
        },
    ]
    return doc(
        "bcrypt",
        "master_password.hash_key = bcrypt(base64(SHA-256(password_utf8))), the "
        "standard (not URL-safe) base64 of the 32-byte digest, 44 ASCII bytes. "
        "Any cost and the $2a$/$2b$ prefixes must verify; new hashes use $2b$ "
        "with cost 12.",
        vectors=vectors,
        mismatches=mismatches,
    )


def backup_entries() -> list[dict]:
    return [
        {
            "name": "GitHub #work",
            "kind": "login",
            "username": "moth@example.com",
            "value": "gh-Secret-1",
            "url": "https://github.com",
            "totp_secret": "JBSWY3DPEHPK3PXP",
            "description": "work account",
            "tags": ["dev", "ops"],
            "custom_fields": [{"label": "Recovery", "value": "abcd", "hidden": True}],
            "folder": "Work",
            "favorite": True,
        },
        {
            "name": "Wi-Fi ключ",
            "kind": "note",
            "username": None,
            "value": "  line one\n\tline two\n\n",
            "url": None,
            "totp_secret": None,
            "description": None,
            "tags": [],
            "custom_fields": [],
            "folder": None,
            "favorite": False,
        },
    ]


def backup_vectors() -> tuple[dict, bytes]:
    password = "Mölle-Stern-2026"
    payload = json.dumps(
        {"exported_at": "2026-10-10T12:00:00+00:00", "passwords": backup_entries()},
        indent=2,
        ensure_ascii=False,
    ).encode("utf-8")
    buffer = io.BytesIO()
    with pyzipper.AESZipFile(
        buffer, "w", compression=pyzipper.ZIP_DEFLATED, encryption=pyzipper.WZ_AES
    ) as zf:
        zf.setpassword(password.encode("utf-8"))
        zf.writestr("ciphermoth_backup.json", payload)
    return (
        doc(
            "backup_zip",
            "Backup format v1: a ZIP with one member, ciphermoth_backup.json, "
            "deflate-compressed and encrypted with WinZip AES-256 (AE-2, "
            "PBKDF2-HMAC-SHA1 with 1000 iterations and a 16-byte salt, as "
            "written by pyzipper) under the UTF-8 master password as submitted "
            "after whitespace stripping. The JSON is {exported_at, passwords: "
            "[{name, kind, username, value, url, totp_secret, description, "
            "tags, custom_fields, folder, favorite}]}; releases before v1.4.0 "
            "wrote only name, username, value, url, totp_secret, description, "
            "tags and favorite. History, trash, attachments, settings and "
            "timestamps are not included.",
            file="backup-v1.zip",
            password=password,
            member="ciphermoth_backup.json",
            json=json.loads(payload),
        ),
        buffer.getvalue(),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    backup_doc, backup_zip = backup_vectors()
    outputs = {
        "argon2id.json": argon2id_vectors(),
        "fernet.json": fernet_vectors(),
        "key_check.json": key_check_vectors(),
        "bcrypt.json": bcrypt_vectors(),
        "backup_zip.json": backup_doc,
    }
    existing = [name for name in [*outputs, "backup-v1.zip"] if (OUT / name).exists()]
    if existing and not args.force:
        print(f"Refusing to overwrite frozen vectors: {existing}", file=sys.stderr)
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    for name, content in outputs.items():
        (OUT / name).write_text(
            json.dumps(content, indent=2, ensure_ascii=False) + "\n"
        )
    (OUT / "backup-v1.zip").write_bytes(backup_zip)
    return 0


if __name__ == "__main__":
    sys.exit(main())
