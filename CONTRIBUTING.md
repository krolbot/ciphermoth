# Contributing & running it your way

This doc is for people who want to **hack on CipherMoth** or **self-host it their own way**, on a real server, behind a proxy, with custom ports. If you just want to run it on your machine, the [README quick start](./README.md#get-started) is all you need; come back here when you want more.

## Development

Clone the repo, then start the dev stack. It builds from your working tree and hot-reloads, and it's a throwaway sandbox with its own database, completely separate from any real vault.

```shell
make setup   # creates backend/.db.env with a generated database password
make dev     # build + start with hot-reload
```

**Open [http://localhost:3000](http://localhost:3000)** (UI) and `http://localhost:8000` (API); the API explorer is at `/docs` on the API port. The backend restarts on any `.py` change and the React dev server picks up frontend changes instantly.

### Dev sandbox vs the real vault

| | Development (local) | Real vault |
|---|---|---|
| Start it with | `make dev` | `docker compose -f docker-compose.prod.yml up -d` (or `make prod-up`) |
| Source | built from your working tree, hot-reload | prebuilt GHCR images |
| Compose project | `ciphermoth-dev` | `ciphermoth` |
| Database volume | `ciphermoth-dev_postgres_data` (disposable) | `ciphermoth_postgres_data` (persistent) |
| UI / API | `:3000` / `:8000` | `:3000` / `:8000` (configurable) |
| Badge in app bar | amber **DEV** | calm **LIVE** |

They are separate Compose projects with separate volumes, so the dev sandbox can never see or clobber your real vault. The environment badge is derived from the build itself (Vite dev server vs `vite build`), so there's nothing to configure. If you ever see amber, you're in the sandbox, don't type anything real.

> Both default to port `3000`. That's fine because dev is local and the real vault runs on your server. If you ever run both on one host, remap the prod ports with `CIPHERMOTH_FRONTEND_PORT` / `CIPHERMOTH_BACKEND_PORT`.

All `make` commands run locally, not inside Docker.

| Command | What it does |
|---|---|
| `make setup` | Create `backend/.db.env` with a generated database password |
| `make dev` | Build and start the dev stack with hot-reload (UI `:3000`, API `:8000`) |
| `make down` | Stop the dev stack, keeping its database volume |
| `make clean` | Remove the dev stack + its volume, delete `__pycache__` |
| `make all` | `clean` then `dev`, a fresh dev sandbox |
| `make prod-up` | Pull and start the real vault from GHCR images (needs a sibling `.env`) |
| `make prod-down` | Stop the real vault, keeping its database volume |
| `make clean-prod` | Destroy the real vault's database volume (guarded, asks to confirm) |
| `make lint` | `ruff check` (backend) + ESLint (frontend) |
| `make typecheck` | `ty check` (backend) |
| `make format` | Auto-format backend (ruff) and frontend (Prettier) |
| `make check` | Lint + type check + format check, no writes, what CI runs |
| `make test` | Backend tests against a throwaway Postgres (needs Docker), then the frontend tests |
| `make test-stress` | Every backend test, including fuzzing with many more examples, random process kills and scale tests |
| `make test-updater-e2e` | Builds release-candidate images and drives real one-click updates, crashes and rollbacks in throwaway Compose projects (needs Docker and network access) |

`make lint/typecheck/format/check` need [uv](https://docs.astral.sh/uv/) with dev deps (`uv sync --group dev` inside `backend/`) and Node.js with npm deps (`npm install` inside `frontend/`).

### Before you push

Run `make check` and `make test`. Together they mirror CI: `ruff check` + `ruff format --check` + `ty check` and pytest on the backend, ESLint + Prettier + Vitest on the frontend. Keep them green.

### Tests

`make test` starts a disposable PostgreSQL in a tmpfs container (`127.0.0.1:55432`), runs the backend suite and removes the container. The suite refuses to run against any database that is not local and named `*_test`, because it truncates tables. To iterate faster, start your own container and run pytest directly:

```shell
cd backend
CIPHERMOTH_TEST_DB_URL=postgresql://ciphermoth_test:ciphermoth_test@127.0.0.1:55432/ciphermoth_test uv run pytest -x
```

What the suite protects, and where:

| Area | Tests |
|---|---|
| Every route rejects missing, forged, expired and locked sessions and forged or stale legacy keys | `test_authz.py`, `test_vault_key.py`, `test_adversarial.py` |
| Vault sessions expire, lock, end on rotation and survive races | `test_sessions.py` |
| Old and new CLIs work with old and new servers | `test_cli.py`, with the released v1.4.7 CLI frozen in `testdata/clients` |
| The frontend image validates its API URL and renders its CSP | `docker/frontend/runtime-config.test.mjs` (part of `make test`) |
| The CSP lets the UI reach its API and blocks every other destination | `docker/frontend/browser/csp.browser.test.mjs`, run with `make test-browser` (builds the image, drives Chromium) |
| Old vaults still open, upgrade and restore | `test_golden.py` with the fixtures in [`testdata/golden`](testdata/golden/README.md) |
| Cryptography is byte-compatible | `test_vectors.py` with [`testdata/vectors`](testdata/vectors/README.md), shared with `frontend/src/lib/totp.test.js` |
| Imports cannot damage a vault | `test_imports.py` (including Hypothesis property tests), `test_hostile_files.py` |
| Failed or interrupted writes change nothing | `test_failures.py`, `test_process_kill.py` |
| The CLI and `scripts/cip` keep their contracts | `test_cli.py` |
| The updater refuses, verifies, snapshots, rolls back and recovers from crashes | `test_updates.py`, `test_updater_recovery.py`, and real updates in Compose with `make test-updater-e2e` |
| Maintenance mode, `/api/health` and the migration gate | `test_maintenance.py`, `test_migration_gate.py` |

Tests authenticate the way current clients do: `auth(token)` sends a session token from `create_vault()` or `unlock()`. `key_auth(key)` with `create_legacy_vault()` or `legacy_unlock()` sends the deprecated vault key header, and `stored_vault_key()` derives the key from the database when a test needs the key itself. The legacy helpers go away with the legacy API in v1.6.0; `test_the_legacy_key_is_removed_on_schedule` fails once the version reaches it.

`backend/tests/integrity.py` reads any vault (any schema from v1.0.0 on) and decrypts every field strictly, reporting what the application's lenient read path would hide. Use it whenever a change touches storage, encryption or migrations: `read_vault` before and after, then `assert_same_vault`.

Property tests run 25 derandomized examples by default so the suite is fast and reproducible; `make test-stress` (or `HYPOTHESIS_PROFILE=stress`) runs hundreds of random ones. Tests marked `@pytest.mark.stress` only run under `make test-stress`.

### Database migrations

Schema is managed with Alembic. The backend runs `alembic upgrade head` automatically on every startup, so you never need to run migrations by hand.

To create a migration after changing a model (needs a running database):

```shell
cd backend
uv run alembic revision --autogenerate -m "describe the change"
```

Migration files land in `migrations/ciphermoth/versions/`.

#### Schema changes and the updater

`test_release_keeps_the_v145_alembic_head` pins the head at `9c0d1e2f3a4b`. The updater now meets the safety contract below (since v1.5.1), but **do not add a revision until updater v2 is widely deployed**: installs update with the updater they already run, and every release before v1.5.1 shipped one that cannot restore a database. Move the pin deliberately, in a release whose notes tell older installs to update the updater first ([docs/UPDATING.md](docs/UPDATING.md)), and fold the startup-added `key_check` column into an idempotent revision (`ADD COLUMN IF NOT EXISTS`) at the same time.

The contract, each item a test in `backend/tests/test_updates.py` (they were strict-xfail until v1.5.1):

1. **No update without a restorable snapshot.** The backend is stopped behind a maintenance flag, the dump is restored into a temporary database and compared table by table; if anything fails the update stops and nothing changes.
2. **Rollback restores the snapshot** before the previous images start, into a fresh database swapped in atomically. Downgrading with Alembic is not enough: `test_downgrade_cannot_roll_back_a_vault_that_uses_the_trash` shows a v1.4.x vault whose trash shares a name with an active entry cannot be downgraded past `5e6f7a8b9c0d`.
3. **An interrupted update is reconciled on restart** from the updater's journal: abandoned before it changed anything, rolled back after, completed once committed. `.env` always ends up naming the version that runs.
4. **The updater updates itself, or tells the user to recreate it.** It never recreates its own container; the result and the UI give the one command, and the backend refuses one-click updates through an updater older than `REQUIRED_UPDATER_PROTOCOL` (`backend/update_protocol.py`).

What keeps the first schema change safe even on old installs:

- `backend/entrypoint.sh` runs `migration_gate.py` before `alembic upgrade head`. With a migration pending, it refuses to start while an updater older than protocol 2 is applying the release (or while a protocol 2 update has no verified snapshot), so an old updater's image-only rollback finds an untouched database. Manual updates are not affected.
- Release images carry `io.ciphermoth.min-updater-protocol`; the updater refuses a release that needs a newer protocol than it speaks. Raise `REQUIRED_UPDATER_PROTOCOL`, the label and `PROTOCOL` in `docker/updater/updater.py` together (`test_migration_gate.py` checks they agree).
- While the updater holds the maintenance flag, the API answers 503 to everything but status checks (`api/maintenance.py`), so a restore after a failed update loses nothing.
- Manual updates (`docker compose pull && up -d`) still migrate with no snapshot and no rollback; the gate deliberately lets them through. Updater v2 support alone is therefore not enough for the first schema-changing release: that release must also define what a manual update does before migrating (for example a pre-migration snapshot in the backend entrypoint) and how a manual user recovers, and its notes must tell manual users to back up first.
- Schema changes go through Alembic only. `crud/runtime_schema.py` (the startup-added `key_check` column) is not gated and must not grow.

Updater tests come in three tiers: `test_updates.py` and `test_updater_recovery.py` drive the real updater against a scripted Docker/PostgreSQL world (`tests/fake_updater_world.py`) and kill it at every step boundary (`CIPHERMOTH_UPDATER_FAULT=kill:<step>`); `make test-updater-e2e` builds the candidate and synthetic future releases (including a migration that fails halfway) and runs real updates, crashes and rollbacks in isolated Compose projects named `cm-e2e-*`, starting from the published previous release and its own updater. Locally built images are unsigned, so the e2e updater images replace `cosign` with a stub that says so; `test_real_cosign_*` use the real one against the published signatures.

## Configuration

Everything is optional, the defaults work fine for local use.

**Backend:**

| Variable | Default | Description |
|---|---|---|
| `CORS_ORIGINS` | `["http://localhost:3000"]` | Allowed frontend origins |
| `DISABLE_DOCS` | `false` | Set `true` to hide `/docs` and `/redoc` |
| `DEBUG` | `false` | FastAPI debug mode |
| `CIPHERMOTH_RATE_LIMIT` | unset | Overrides every route's own limit (e.g. `200/hour`). Unlocking defaults to `30/hour`; each CLI command unlocks once, so raise this if a batch of them trips it |
| `CIPHERMOTH_LEGACY_KEY_AUTH` | `true` | Set `false` to refuse clients from v1.4.x and earlier, which receive the vault key and send it back with every request. This compatibility is removed in v1.6.0. Compose files from before v1.5.0 don't pass it on; add it to the backend's `environment` and confirm `/api/meta` no longer lists `legacy-key-auth` |

**Frontend:**

| Variable | Default | Description |
|---|---|---|
| `VITE_API_URL` | `http://localhost:8000/api` | Backend API base URL: an `http(s)` URL, a `//host` URL, or a path such as `/api` when a proxy serves the API on the UI's own origin. The image allows browser connections only to this origin (plus GitHub's release address for the update check). A value with another scheme or with characters that could rewrite the policy or the app is refused: the UI then shows a page explaining what to fix. With an IPv6 address the policy can only restrict the scheme (`http:`/`https:`), so prefer a host name. In Compose it comes from `CIPHERMOTH_API_URL` |

**CLI:**

| Variable | Default | Description |
|---|---|---|
| `CIPHERMOTH_API_URL` | `http://localhost:8000/api` | Backend API base URL (baked to `http://localhost/api` inside the backend image) |
| `CIPHERMOTH_COMPOSE_FILE` | `<cip's folder>/docker-compose.prod.yml` | Compose file the `cip` wrapper drives |

The CLI warns before prompting if `CIPHERMOTH_API_URL` points at a remote host over plain HTTP, since the master password would cross the network unencrypted. See [docs/CLI.md](./docs/CLI.md).

## Putting it on a real server

CipherMoth is built to run on a machine you trust, your home server, a VPS behind a firewall, a Raspberry Pi in your closet, not to sit naked on the open internet. If you're deploying it somewhere reachable:

- Set `CIPHERMOTH_FRONTEND_ORIGIN` / `CORS_ORIGINS` to your actual domain and enable `DISABLE_DOCS=true`
- Put everything behind a reverse proxy (nginx, Caddy) with HTTPS, and have it pass request paths through **unchanged** (see below)
- Don't expose Postgres (port `5432`) to the outside world

`docker-compose.prod.yml` publishes the UI and API on `127.0.0.1` only. That is what you want when the reverse proxy runs on the same host: the proxy can reach CipherMoth, nothing else on the network can. If other machines need to reach the ports directly (a proxy on another box, a LAN, a VPN such as Tailscale), set `CIPHERMOTH_BIND_ADDRESS=0.0.0.0` in your `.env`, or a specific interface address, and make sure HTTPS sits in front. Installs from before v1.4.6 keep whatever their own copy of the compose file says until it is replaced.

**Pass request paths through unchanged.** Entry names can contain `/`, which clients send as `%2F`. A proxy that decodes `%2F` before forwarding turns a request for the entry `x/purge` into a request to purge the entry `x`. Caddy's `reverse_proxy` (also inside `handle_path`) and nginx's `proxy_pass http://127.0.0.1:8000;` (no path after the address) pass the path unchanged. nginx's `proxy_pass http://127.0.0.1:8000/;` or `.../api/;` (with a path, including any path-prefix setup) decodes it. Since v1.4.7 the web UI and CLI also name the entry in a header, so the API refuses such a rewritten request instead of acting on another entry, but older clients get no such protection and the entries stay unreachable until the proxy is fixed.

Vault sessions live in the backend's memory. Run exactly one backend process (the image's `uvicorn --workers 1`); with several workers a session opened by one would be unknown to the others. The session token travels in the `x-ciphermoth-session` header, which proxies forward by default; don't log it, because it opens the vault until the session ends. `Authorization` is left to the proxy, so Basic auth or a forward-auth login in front of CipherMoth keeps working.

One thing to know about rate limiting behind a proxy: the limits are keyed on the client IP, which the app reads from the network connection. Behind a reverse proxy every request looks like it comes from the proxy, so the limits become global instead of per client. If you want per-client rate limiting, configure your proxy to preserve the real client address (and only trust `X-Forwarded-For` from the proxy itself).

## Staying up to date

CipherMoth notices when a newer release is out and shows an **Update** chip in the app bar. The check runs **in your browser** against GitHub's public API, the server never phones home, and you can turn it off under Settings, "Check for updates", if you'd rather your instance talk to nobody at all.

**Updating by hand** (always available): edit `CIPHERMOTH_VERSION` in your `.env` (or leave it `latest`) and re-run:

```shell
docker compose -f docker-compose.prod.yml pull && \
docker compose -f docker-compose.prod.yml up -d
```

**One-click updates** (opt-in): if you'd like the **Update** button to do this for you, start the stack with the self-updater enabled (the installer offers to do this for you):

```shell
docker compose -f docker-compose.prod.yml --profile autoupdate up -d
# from a repo clone you can also use: make prod-up-autoupdate
```

This adds a small `updater` container that holds the Docker socket. Because it can restart your stack, it's **off by default** and deliberately careful:

- It **verifies every image is signed** (cosign / Sigstore) by CipherMoth's official release workflow before running it, a compromised registry alone can't slip you a malicious build. That includes the version it would roll back to.
- It takes a **verified database snapshot** (restored and compared before it continues), and if the new version or its database migration fails, it **restores the snapshot and the previous version automatically**. While it works, the API pauses writes, so nothing you save is lost.
- It survives being interrupted: after a crash or a reboot it finishes or rolls back from its journal.
- It has **no network listener**, it only reacts to a file the backend writes after an unlocked-vault, rate-limited request. Your master password is never involved.

If the updater isn't enabled, the button simply shows you the manual command above. Updaters from v1.5.0 and older need a one-time upgrade after you reach v1.5.1; the app shows the command. Details, snapshots and manual recovery: [docs/UPDATING.md](docs/UPDATING.md).
