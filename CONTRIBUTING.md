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
| Every route rejects missing, forged and stale keys | `test_authz.py`, `test_vault_key.py`, `test_adversarial.py` |
| Old vaults still open, upgrade and restore | `test_golden.py` with the fixtures in [`testdata/golden`](testdata/golden/README.md) |
| Cryptography is byte-compatible | `test_vectors.py` with [`testdata/vectors`](testdata/vectors/README.md), shared with `frontend/src/lib/totp.test.js` |
| Imports cannot damage a vault | `test_imports.py` (including Hypothesis property tests), `test_hostile_files.py` |
| Failed or interrupted writes change nothing | `test_failures.py`, `test_process_kill.py` |
| The CLI and `scripts/cip` keep their contracts | `test_cli.py` |
| The updater refuses, verifies and rolls back | `test_updates.py` |

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

**Do not add an Alembic revision yet.** `test_release_keeps_the_v145_alembic_head` pins the head at `9c0d1e2f3a4b`, and it should only move once the one-click updater meets the contract below. The reason: an image that predates a revision refuses to start against the migrated schema, so the updater's automatic rollback (restart the previous images) would leave the vault offline. Existing installs also apply an update with the updater they already run, so the updater must be fixed, released and widely deployed **before** the first release that migrates.

The contract, each item pinned by an `xfail(strict=True)` test in `backend/tests/test_updates.py` that will start failing (and must then be un-marked) once it holds:

1. **No update without a restorable snapshot.** If `pg_dump` fails, the update is refused and nothing changes. Today it logs a warning and continues.
2. **Rollback restores the snapshot** taken before the update, before the previous images start. Downgrading with Alembic is not enough: `test_downgrade_cannot_roll_back_a_vault_that_uses_the_trash` shows a v1.4.x vault whose trash shares a name with an active entry cannot be downgraded past `5e6f7a8b9c0d`.
3. **An interrupted update is reconciled on restart**: the result never stays `applying`, and `.env` matches the version that is running.
4. **The updater updates itself**, or tells the user to recreate it.

Writes made between the snapshot and a rollback are lost by a snapshot restore; the updater must say so. When all four hold, fold the startup-added `key_check` column into an idempotent revision (`ADD COLUMN IF NOT EXISTS`) and move the pinned head.

## Configuration

Everything is optional, the defaults work fine for local use.

**Backend:**

| Variable | Default | Description |
|---|---|---|
| `CORS_ORIGINS` | `["http://localhost:3000"]` | Allowed frontend origins |
| `DISABLE_DOCS` | `false` | Set `true` to hide `/docs` and `/redoc` |
| `DEBUG` | `false` | FastAPI debug mode |
| `CIPHERMOTH_RATE_LIMIT` | unset | Overrides every route's own limit (e.g. `200/hour`). Unlocking defaults to `30/hour`; each CLI command unlocks once, so raise this if a batch of them trips it |

**Frontend:**

| Variable | Default | Description |
|---|---|---|
| `VITE_API_URL` | `http://localhost:8000/api` | Backend API base URL |

**CLI:**

| Variable | Default | Description |
|---|---|---|
| `CIPHERMOTH_API_URL` | `http://localhost:8000/api` | Backend API base URL (baked to `http://localhost/api` inside the backend image) |
| `CIPHERMOTH_COMPOSE_FILE` | `<cip's folder>/docker-compose.prod.yml` | Compose file the `cip` wrapper drives |

The CLI warns before prompting if `CIPHERMOTH_API_URL` points at a remote host over plain HTTP, since the master password would cross the network unencrypted. See [docs/CLI.md](./docs/CLI.md).

## Putting it on a real server

CipherMoth is built to run on a machine you trust, your home server, a VPS behind a firewall, a Raspberry Pi in your closet, not to sit naked on the open internet. If you're deploying it somewhere reachable:

- Set `CIPHERMOTH_FRONTEND_ORIGIN` / `CORS_ORIGINS` to your actual domain and enable `DISABLE_DOCS=true`
- Put everything behind a reverse proxy (nginx, Caddy) with HTTPS
- Don't expose Postgres (port `5432`) to the outside world

`docker-compose.prod.yml` publishes the UI and API on `127.0.0.1` only. That is what you want when the reverse proxy runs on the same host: the proxy can reach CipherMoth, nothing else on the network can. If other machines need to reach the ports directly (a proxy on another box, a LAN, a VPN such as Tailscale), set `CIPHERMOTH_BIND_ADDRESS=0.0.0.0` in your `.env`, or a specific interface address, and make sure HTTPS sits in front. Installs from before v1.4.6 keep whatever their own copy of the compose file says until it is replaced.

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

- It **verifies every image is signed** (cosign / Sigstore) by CipherMoth's official release workflow before running it, a compromised registry alone can't slip you a malicious build.
- It **snapshots the database** before applying and **rolls back automatically** if the new version fails its health check.
- It has **no network listener**, it only reacts to a file the backend writes after an unlocked-vault, rate-limited request. Your master password is never involved.

If the updater isn't enabled, the button simply shows you the manual command above.
