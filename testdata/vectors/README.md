# CipherMoth cryptographic test vectors

Frozen known-answer vectors for every cryptographic construction a CipherMoth vault depends on. They exist so that any implementation (the Python backend today, a TypeScript, Rust or mobile core later) can prove it reads and writes the same vault format. All values are synthetic.

**Frozen means frozen.** A vector never changes once committed. If the format changes, add a new file or a new section and keep the old one, because existing vaults and backups keep using the old format forever.

The Python tests are in `backend/tests/test_vectors.py`; the frontend runs `totp.json` in `frontend/src/lib/totp.test.js`.

## Files

Every JSON file has `format` (`ciphermoth-test-vectors/1`), `name` and `description`, then its vectors. Byte strings are lowercase hex (`*_hex`); keys and tokens are the ASCII strings as stored.

| File | Covers |
|---|---|
| `argon2id.json` | Vault key derivation, plus `api_input`: which characters the API strips from a master password before it reaches the KDF |
| `fernet.json` | Encrypted column format: valid tokens with fixed IV and timestamp, and tokens that must be refused |
| `key_check.json` | The key-check token and the keys that must be refused |
| `bcrypt.json` | Master password verification, including passwords longer than 72 bytes and the pre-v0.3.0 scheme that is not supported |
| `totp.json` | RFC 6238 TOTP for stored secrets |
| `backup_zip.json` + `backup-v1.zip` | The v1 backup ZIP: a real archive, its password and its JSON |

## The constructions

**Master password input.** The API strips leading and trailing Unicode `White_Space` (pydantic's `str_strip_whitespace`), then encodes UTF-8. No Unicode normalization: NFC and NFD forms of the same password are different passwords. Characters that are not `White_Space`, such as U+200B or U+001C, are kept even though Python's `str.strip()` would remove U+001C.

**Vault key.** `base64url(Argon2id(password, salt, m=65536 KiB, t=3, p=4, length=32))`, version 0x13, no secret or associated data, 16-byte random salt stored in `master_password.salt`. The 44-character string, with `=` padding, is the Fernet key. Clients of v1.4.x received it and sent it back in the `x-ciphermoth-key-derivation` header; since v1.6.0 it never leaves the server.

**Encrypted columns.** Fernet, spec version `0x80`: `base64url(0x80 || timestamp (u64 big-endian) || IV (16) || AES-128-CBC(key[16:32], PKCS7(plaintext)) || HMAC-SHA256(key[0:16], everything before))`. Columns hold the ASCII bytes of the token. Text is UTF-8, JSON columns (`tags`, `custom_fields`, `password_history`) are UTF-8 JSON, attachment content is raw bytes. No TTL is enforced.

**Key check.** `master_password.key_check` is a Fernet token of `"ciphermoth-key-check-v1:" || salt`. A presented key is accepted only if it is the canonical encoding (decoding and re-encoding gives the same 44 characters) and the token decrypts to exactly that plaintext. Comparing plaintext matters: a key with the right signing half and a wrong encryption half passes the HMAC.

**Master password hash.** `bcrypt(base64(SHA-256(password)))`, standard base64 of the digest (44 bytes, below bcrypt's 72-byte limit, so the whole password counts). New hashes are `$2b$12$`. Vaults from before v0.3.0 used plain bcrypt and cannot be opened.

**TOTP.** RFC 6238 with HMAC-SHA1. Secrets are stored upper-case, unpadded base32 with no spaces; pad to a multiple of 8 before decoding.

**Backup ZIP (v1).** One member, `ciphermoth_backup.json`, deflated and encrypted with WinZip AES-256 (AE-2; PBKDF2-HMAC-SHA1, 1000 iterations, 16-byte salt) under the UTF-8 master password. It is a lossy export: no history, trash, attachments, settings or timestamps.

## Regenerating

`backend/tests/tools/generate_vectors.py` is the reference construction, written against the primitive libraries rather than the application code. It refuses to overwrite existing files. A test checks that it still reproduces the frozen JSON byte for byte, so a library upgrade that changed any output would fail loudly instead of being frozen in. `backup-v1.zip` cannot be reproduced (the ZIP salt is random) and is only ever read.
