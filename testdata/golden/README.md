# Golden vault fixtures

One synthetic vault per release that changed the stored format, created by **that release's own code** and frozen. The tests in `backend/tests/test_golden.py` prove that today's code still opens, upgrades, decrypts, rotates and restores each of them. All credentials and contents are synthetic.

| Fixture | Built from | Schema (Alembic head) | What it represents |
|---|---|---|---|
| `v0.3.0` | the `v0.3.0` git tag (Dinopass; no published image) | `3c4d5e6f7a8b` | Last pre-rebrand release, first with the SHA-256 pre-hash for bcrypt |
| `v1.0.0` | `ghcr.io/mr-grj/ciphermoth-backend:1.0.0` | `3c4d5e6f7a8b` | First CipherMoth release |
| `v1.1.0` | `ghcr.io/mr-grj/ciphermoth-backend:1.1.0` | `4d5e6f7a8b9c` | Adds `settings.update_check_enabled` (unchanged through v1.3.1) |
| `v1.4.0` | `ghcr.io/mr-grj/ciphermoth-backend:1.4.0` | `9c0d1e2f3a4b` | Trash, custom fields, folders, secure notes, attachments |
| `v1.4.5` | `ghcr.io/mr-grj/ciphermoth-backend:1.4.5` | `9c0d1e2f3a4b` | Last release before the key check |
| `v1.4.6` | `ghcr.io/mr-grj/ciphermoth-backend:1.4.6` | `9c0d1e2f3a4b` + `key_check` | Key check column added at startup |

The exact image digest or tag commit is recorded in each `expected.json` (`provenance`).

## What each fixture contains

- `dump.sql`: `pg_dump --column-inserts` of the vault's database right after seeding, with psql meta-commands removed so it loads through any client.
- `backup.zip`: a backup exported through that release's API.
- `expected.json`: the master password, the key that release derived, and everything read back through that release's own API (active entries, trash, attachment digests, settings). Tests compare against this, so a fixture asserts what the release actually stored, including its quirks: releases before v1.4.0 stripped whitespace around password values.

Every vault was created with one master password and rotated to a second one midway, so half of the ciphertext was written by the release's rotation code. Contents: logins with every field, Unicode and emoji names and values, URL-reserved characters in names, a password changed 12 times (history kept at 10), 20 maximum-length tags, maximum-length name, username, URL, description and a 4 KB value, changed settings, and from v1.4.0 a secure note with trailing whitespace, 30 custom fields including a 4096-character value, folders, a trashed entry that shares its name with an active one, and binary attachments including invalid UTF-8 and a non-ASCII filename (on active and trashed entries, before and after the rotation).

## Compatibility verified by the tests

| Source | Vault database | Backup ZIP |
|---|---|---|
| Before v0.3.0 (Dinopass) | **Not supported**: plain bcrypt hashes cannot be verified (see `vectors/bcrypt.json`) | Not tested |
| v0.3.0 (Dinopass) | Supported: same migration chain and cryptography as v1.0.0 | **Not importable**: the member is `dinopass_backup.json`. Restore it into v0.3.0 and back up again from a current release, or rename the member inside the archive |
| v1.0.0 to v1.4.6 | Supported | Supported (lossy by design: no history, trash, attachments or settings) |

## Regenerating

Fixtures are frozen and should not be regenerated; add a new directory for a new release that changes the format. The generator is `backend/tests/tools/generate_golden.py` (`uv run python -m tests.tools.generate_golden v1.4.6`, refuses to overwrite). It runs everything in a throwaway Docker network with a tmpfs database and removes it afterwards.
