<div align="center">

# CipherMoth

**Your secrets stay in the dark.**

A simple, self-hosted password manager with **no accounts, no cloud, and no witnesses.**

[![CI](https://github.com/mr-grj/ciphermoth/actions/workflows/ci.yml/badge.svg)](https://github.com/mr-grj/ciphermoth/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/mr-grj/ciphermoth?color=000000&label=release)](https://github.com/mr-grj/ciphermoth/releases/latest)
[![License](https://img.shields.io/badge/license-MIT-000000.svg)](./LICENSE)
[![Python](https://img.shields.io/badge/python-3.13-000000.svg)](https://www.python.org/)
[![SQLite](https://img.shields.io/badge/sqlite-3.53-000000.svg)](https://www.sqlite.org/)
[![Self-hosted](https://img.shields.io/badge/self--hosted-7dd3c0.svg?labelColor=000000)](#get-started)

</div>

---

## What is this?

I built this for myself because I was tired of every password manager wanting my email address, a subscription, a
browser extension with access to everything, and ideally my soul too. Most of the big ones lean on a hosted account,
a sync layer, or a monthly bill by default.

I wanted something that lives on my own machine, has no telemetry, talks to no third party, and doesn't wake up one day
to announce it's been acquired and migrating to some new platform. No Google. No OAuth. No analytics pinging home. Nothing.

So there's **CipherMoth**. It lives on your hardware, speaks to nobody, and keeps the passwords encrypted with a key only
you know. One master password unlocks everything. If someone gets the vault file, they get encrypted blobs, not your passwords.

## Screenshots

|  |  |
|---|---|
| **First run: set up your master password** | **The vault** |
| ![Set up your vault](docs/screenshots/00-login.png) | ![Vault overview](docs/screenshots/01-vault.png) |
| **Add a password, generate a strong one** | **Vault health, computed on your device** |
| ![Add password with generator](docs/screenshots/02-add-generator.png) | ![Vault health report](docs/screenshots/03-health.png) |

## Get started

CipherMoth runs on your own machine with [Docker](https://docs.docker.com/get-docker/): two containers and one volume, no
database server, nothing to configure. One command pulls the release images (signed with cosign; [docs/UPDATING.md](./docs/UPDATING.md) shows how to verify them) and starts everything:

```shell
curl -fsSL https://raw.githubusercontent.com/mr-grj/ciphermoth/master/install.sh | sh
```

Open **[http://localhost:3000](http://localhost:3000)**, create your master password, and you're in. The whole vault is
one SQLite file in a persistent Docker volume, so it survives restarts and updates, and a consistent snapshot of it is
one command away (`ciphermoth-admin snapshot`, see [docs/UPDATING.md](./docs/UPDATING.md)).

> Coming from CipherMoth 2.0? **3.0 requires a new vault** and refuses the old file unchanged. Export active entries
> in 2.0 first, preserve the old vault explicitly, then create a new vault and import the ZIP. Follow the
> [complete upgrade procedure](./docs/UPDATING.md#moving-from-ciphermoth-20-vault-format-1).
>
> Coming from CipherMoth 1.x (PostgreSQL)? This release needs a fresh install with a new vault; it never reads or deletes
> your old database. The steps, and how to bring your entries along, are in [docs/UPDATING.md](./docs/UPDATING.md#moving-from-a-postgresql-release-v160-and-older).

Rather read the script before piping it to a shell, set it up by hand, run it on a real server, or tweak the config?
That's all in **[CONTRIBUTING.md](./CONTRIBUTING.md)**.

> ⚠️ **There is no password recovery.** Losing your master password means losing your vault, permanently. No reset link,
> no support email, no backdoor. That's the trade for nobody-but-you holding the key. **Write it down somewhere safe**,
> and take a backup once you've added a few entries.

## What it does

- one master password unlocks the vault, no account, no email, no recovery codes sent to a phone number you changed three years ago
- all entry contents encrypted at rest with a random vault key, stored only wrapped under a key derived from your master password
- store a username, website, tags, folders, a two-factor (TOTP) secret, and your own custom fields alongside each entry, all encrypted, entry names included (see [Security](#security))
- built-in two-factor: paste a 2FA secret, and CipherMoth shows the live rolling code, computed in the browser
- secure notes for free-form secrets (recovery codes, Wi-Fi, passport details), encrypted just like passwords
- attach files to any entry (recovery-code PDFs, license keys, key files), up to 5 MB each, encrypted with your vault key
- search, favorites, folders, tags, and password history to keep a growing vault tidy
- trash for deletions you can restore from or empty for good when you're sure
- light and dark themes that flip across the whole app, toggled by a moth that flutters off as the colours fade (and remembers your pick)
- vault health check that flags weak, reused, and old passwords, entirely on your device
- cryptographically secure password generator (not the `Math.random()` kind) with a strength indicator on every entry
- import from Chrome, Bitwarden, KeePass, Proton Pass, and friends via CSV
- complete encrypted backups (`.cmbackup`): every entry, the trash, password history, attachments and settings, restorable into this vault or a new one
- a CLI (`ciphermoth`) for the terminal, and auto-lock plus clipboard-clearing (for the small things that matter ^^)
- notices new releases (from your browser, never the server) and shows the commands to update, with a consistent, integrity-checked snapshot of the vault first; release images are signed (Sigstore / cosign)

## Who it's for (and who it isn't)

CipherMoth is probably a good fit if you:

- want a self-hosted password manager with no accounts, no telemetry, and no third parties
- are comfortable running Docker on a machine you control
- like small, auditable software and are happy owning your own backups

It's probably not for you (yet) if you need browser autofill, a mobile app, family or team sharing, managed cloud sync,
or a way to recover your vault if you forget your master password. No hard feelings, those are real needs, just not what
this is trying to be.

## Security

Straight up, because this is a password manager and you deserve it: **CipherMoth has not been independently audited.**
It's a personal project I use myself and built carefully, with the crypto kept small and readable on purpose, but it has
not been through a formal third-party security review. It's designed for self-hosted personal use on hardware you trust,
not as a public, multi-tenant service holding other people's secrets. Weigh that accordingly.

How it works (the full specification is [docs/VAULT_FORMAT.md](./docs/VAULT_FORMAT.md)):

- each vault has a random 256-bit **vault key**. It is stored only wrapped (AES-256-GCM) under a key derived from your
  master password with **Argon2id** (OWASP 2024 interactive profile, a random salt per vault). There is no separate
  password hash: a wrong master password simply cannot unwrap the key, and guessing costs one Argon2id run per try.
  New vaults require a reasonably strong master password (12+ characters, mixed types), enforced on the server;
- **everything you put in an entry is encrypted** with **AES-256-GCM**: its name, username, password or note, website,
  2FA secret, description, tags, folder, custom fields, password history, favorite flag and type, and each attachment's
  name, type and bytes. Every encrypted value is bound to its own record, so it cannot be swapped into another entry
  without being detected. Entries are found by name through a keyed hash (HMAC-SHA256) of the name, never a plaintext
  copy;
- **what the vault file still shows** without your master password: how many entries and attachments there are, which
  ones are in the trash, timestamps, attachment sizes, approximate entry sizes, which entries share a name (an entry and
  its trashed copies) and your timeout settings. This is encryption of each entry, not of the whole file;
- changing the master password creates a new vault key and re-encrypts everything, so the old password and the old key
  open nothing in the vault afterwards (older snapshots and backups keep the password they were made with);
- when you unlock, the server unwraps the key and keeps it in memory for a **session**; your browser and the CLI only
  get a random session token (the browser keeps it in `sessionStorage` for that tab), never the key, and no route
  hands the key out or accepts it back. The server ends the session after the inactivity timeout from Settings, when
  you log out, when the master password changes, and when it restarts (closing a tab without logging out leaves its
  session until the timeout), and never stores or logs the key or the token. While you're using the vault, the
  server process does handle the key and your passwords in plaintext: run it on a machine you trust;
- a strict Content-Security-Policy restricts the web UI to connecting to its own API (and GitHub's release address
  for the update check);
- **backups** (`.cmbackup`) are complete and authenticated: every entry including the trash and history, attachments
  byte for byte, and your settings, encrypted with AES-256-GCM under Argon2id with the backup's own random salt and
  your master password. A wrong password, a damaged or cut-off file changes nothing on restore. A backup is the
  portable copy; a **snapshot** (`ciphermoth-admin snapshot`, see [docs/UPDATING.md](./docs/UPDATING.md#snapshots))
  is a raw local copy of the vault file for recovering this installation. Check that a browser download actually
  saved the backup file; the app cannot verify browser saving and does not label entries as safely backed up;
- the UI and API listen on `127.0.0.1` by default; exposing them to other machines is an explicit setting;
- the password generator uses `crypto.getRandomValues` with rejection sampling, no `Math.random()`, no shortcuts;

**It protects against** someone who steals the vault file, a snapshot, a backup or the disk (they get ciphertext and
the counts and timestamps listed above, and each password guess costs a full Argon2id run), someone who edits the file
without your master password (changes to encrypted data are detected and the vault refuses to show it), accidental
server-side exposure (the server never persists the master password, the vault key or session tokens), and casual
inspection of stored data. A session token that leaks works only until that session ends; it never reveals the key.

**It does not protect against** malware or a keylogger on the device you unlock from, a weak master password, exposing
the instance on the public internet without `https`, someone with write access to the vault file rolling it back to an
older copy or deleting entries, or forgetting your master password (there is no recovery). Run it on a machine and
network you trust, use a strong master password, and keep a backup.

To report a vulnerability, see [SECURITY.md](./SECURITY.md).

## Tech stack

| Layer | Tech |
|---|---|
| Backend | Python 3.13, FastAPI, SQLAlchemy 2.0, aiosqlite |
| Database | SQLite 3.53 (one file, WAL, full sync) |
| Frontend | React 19, Vite, MUI v9, easy-peasy |
| Package manager | uv (backend), npm (frontend) |
| Infrastructure | Docker, Docker Compose v2 |

## Docs

- **[CONTRIBUTING.md](./CONTRIBUTING.md)** - hacking on CipherMoth, self-hosting on a server, configuration, and updates
- **[docs/UPDATING.md](./docs/UPDATING.md)** - updating, snapshots, restoring a snapshot, and moving from a PostgreSQL install
- **[docs/CLI.md](./docs/CLI.md)** - the `ciphermoth` command-line reference. A plain Docker install already has it: `install.sh` leaves a `cip` script in your CipherMoth folder, so `./cip password list` just works (no Python, no clone)
- **[SECURITY.md](./SECURITY.md)** - reporting a vulnerability
- Logo, wordmark, and favicon live in [`docs/brand/`](./docs/brand)

## License

MIT: see [LICENSE](./LICENSE).

## Desktop alpha development

A local Tauri desktop alpha now uses the same v3 Python core and encrypted SQLite vault without Docker. See [desktop setup and validation](desktop/README.md). Desktop installers are not publicly distributed yet; the server installation above remains supported.
