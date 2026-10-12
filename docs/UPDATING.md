# Updating CipherMoth

There are two ways to update a self-hosted CipherMoth: by hand, or with the opt-in one-click updater. Both keep your vault in its Docker volume; neither ever needs your master password.

## By hand

Back up first (Settings, "Back up", or `cip backup`). Then, in your CipherMoth folder:

```shell
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
```

`CIPHERMOTH_VERSION` in `.env` decides which release runs (`latest`, or a pinned version such as `1.5.1`). Nothing verifies the images' signatures on this path unless you do it yourself (see [SECURITY.md](../SECURITY.md)), and nothing rolls back for you.

## One-click updates

Start the stack with the `autoupdate` profile (the installer offers this):

```shell
docker compose -f docker-compose.prod.yml --profile autoupdate up -d
```

This adds a small `updater` container that holds the Docker socket. It has no network listener; it acts only on a request file the backend writes after an unlocked, rate-limited request from the web UI. The **Update** button in the app then:

1. **Checks** that the request is valid, recent and new, that the target is newer than what runs, and that CipherMoth is fully healthy (backend and web UI) before touching anything.
2. **Verifies** with cosign that the new backend and frontend images are signed by CipherMoth's release workflow, and that the images running now (the rollback target) are too. It refuses a release that declares it needs a newer updater, and a compose file that would run other images than the verified ones.
3. **Takes a verified snapshot.** It puts the API into maintenance mode, stops the backend, dumps the database (`pg_dump`, custom format), restores the dump into a temporary database and compares every table, sequence and the schema with the live database. Only a dump that restores identically is kept. If any of this fails, the backend is restarted unchanged and the update stops: nothing was changed.
4. **Applies** the update: `.env` is rewritten atomically to the new version and the new images start. The new backend migrates the database if the release needs it.
5. **Validates** the new version: the backend reports the new version and a database at the release's schema, and the web UI serves the real application (page, script, security policy, configuration) at the same version. It must stay healthy for several checks in a row.
6. **Commits**, leaves maintenance mode, and keeps the last three snapshots.

If anything fails after step 3, it **rolls back**: it stops the new version, restores the snapshot into a fresh database and swaps it in atomically, restores `.env` byte for byte and the exact previous images, starts them and checks their health. While an update runs, the API answers `503` to everything except status checks, so a snapshot restore can never lose something you saved: nothing can be saved between the snapshot and the end of the update.

### What is guaranteed

- No update runs without a snapshot that was proven to restore.
- A failed update, including a failed or half-applied database migration, ends with the previous version running on the database exactly as it was before the update.
- Only images signed by the official release workflow run, forward or backward, and only newer releases are installed.
- The updater can be killed at any moment (a crash, `docker stop`, a reboot, power loss): when it starts again it finishes what it was doing from its journal. An update that had not changed anything yet is abandoned, one that had is rolled back, one that was already committed is completed. Each step can be repeated safely, and retries are bounded.
- A successful update means both the backend and the web UI work at the new version.

### What is not

- The updater checks CipherMoth's own containers on Docker's internal network. It cannot see your reverse proxy, TLS certificates or DNS.
- Changes you make to `.env` while an update is running are undone if it rolls back.
- If the updater is stopped for good in the middle of an update, the API stays in maintenance mode until it runs again (start it, and it recovers) or until you recover by hand (below).
- If Docker or the database is still unavailable ten minutes after the updater starts (`DEPENDENCY_TIMEOUT`), it exits and Docker's restart policy starts it again later; nothing is changed meanwhile.

## Updating the updater

The updater only updates `backend` and `frontend`; it never replaces itself, because a container that recreates itself through Compose is killed halfway through doing so. Updating it is one command, and CipherMoth tells you when you need it:

```shell
docker compose -f docker-compose.prod.yml --profile autoupdate pull updater
docker compose -f docker-compose.prod.yml --profile autoupdate up -d --no-deps updater
```

This recreates only the updater, with the image of the version in your `.env`; it does not touch your vault or restart the app. Run it when no update is in progress.

### From v1.5.0 or older (one time)

Updaters shipped before v1.5.1 (protocol 1) can install v1.5.1 itself, which changes nothing in the database, but they cannot restore a database if an update fails. So:

1. Update to v1.5.1. While v1.5.1 is the newest release, one click does it. Once a newer release exists, the old app always offers the newest one, so set `CIPHERMOTH_VERSION=1.5.1` in `.env` and run:

   ```shell
   docker compose -f docker-compose.prod.yml --profile autoupdate pull
   docker compose -f docker-compose.prod.yml --profile autoupdate up -d
   ```

   This brings v1.5.1 and its updater in one step (skip step 2).
2. After a one-click update to v1.5.1, the update dialog shows the command above. Run it once.
3. The dialog now offers one-click updates again, with the new updater (protocol 2).

From v1.5.1 on, the backend refuses one-click requests until the updater speaks protocol 2. Releases that change the database schema also refuse to migrate while an older updater is installing them: the new backend stops before touching the database (its log says why), and the old updater rolls back to the version you had. Updating by hand is unaffected, except within ten minutes of an attempt by an updater from v1.4.3 or older, whose status the new backend cannot read: it waits that long before migrating.

Check what is running with `docker compose -f docker-compose.prod.yml --profile autoupdate exec updater updater.sh status`, or look at `updater_protocol` in `GET /api/updates/apply/status`.

## Snapshots

Snapshots live in the `update_backups` volume, readable only by root inside the updater container:

- `/backups/snapshots/<time>-<id>.dump`: the database in PostgreSQL's custom format (`pg_restore` reads it), mode 0600.
- `/backups/snapshots/<time>-<id>.json`: its manifest (SHA-256, size, PostgreSQL and CipherMoth versions, and a fingerprint of every table).
- `/backups/state/`: the updater's journal.
- `/backups/ciphermoth-*.sql`: plain dumps left by updaters before v1.5.1. The new updater leaves them alone; delete them when you no longer need them.

A snapshot holds what the database holds: encrypted entries, the bcrypt hash of your master password, and the entry names, usernames and descriptions that are not encrypted yet. Treat the volume like the database volume. The updater keeps the three most recent snapshots (`SNAPSHOT_KEEP`) and needs free space for one more plus a temporary copy of the database while it verifies it. The database password reaches the PostgreSQL tools through a private password file, never through command lines or logs.

## Manual recovery

The updater stops and asks for help (state `intervention`) only when it cannot restore the previous version on its own: the snapshot is missing or damaged, or the rollback keeps failing (for example because the disk is full). It then keeps the API in maintenance mode, keeps the snapshot and the database the failed version left behind, and refuses further updates.

1. See what happened:

   ```shell
   docker compose -f docker-compose.prod.yml --profile autoupdate logs --tail 200 updater
   docker compose -f docker-compose.prod.yml --profile autoupdate exec updater updater.sh status
   docker compose -f docker-compose.prod.yml --profile autoupdate exec updater ls -l /backups/snapshots
   ```

   `status` shows the previous version (`previous.version`), the snapshot (`snapshot.name`) and the last error.

2. Fix the cause if you can (free disk space, start the database), then ask the updater to try again. It repeats the recovery it was doing, from the start, with a fresh retry budget:

   ```shell
   docker compose -f docker-compose.prod.yml --profile autoupdate exec updater updater.sh retry
   ```

   If it still reports `intervention`, continue by hand.

3. Check whether the updater already swapped the snapshot in:

   ```shell
   docker compose -f docker-compose.prod.yml exec db psql -U ciphermoth -d postgres -Atc \
     "SELECT datname FROM pg_database WHERE datname LIKE 'ciphermoth%'"
   ```

   If a `ciphermoth_failed_<id>` database exists, `ciphermoth` already holds the restored snapshot: skip to step 4. Otherwise stop the app, restore the snapshot into a new database and swap it in (replace `<name>`):

   ```shell
   docker compose -f docker-compose.prod.yml stop backend frontend
   docker compose -f docker-compose.prod.yml exec db createdb -U ciphermoth ciphermoth_restored
   docker compose -f docker-compose.prod.yml --profile autoupdate exec updater sh -c \
     'PGPASSFILE=/tmp/ciphermoth-updater.pgpass pg_restore -h db -U "$POSTGRES_USER" \
      -d ciphermoth_restored --exit-on-error --single-transaction /backups/snapshots/<name>.dump'
   docker compose -f docker-compose.prod.yml exec db psql -U ciphermoth -d postgres -c \
     'ALTER DATABASE ciphermoth RENAME TO ciphermoth_failed_manual; ALTER DATABASE ciphermoth_restored RENAME TO ciphermoth;'
   ```

   Use your own `POSTGRES_USER` and `POSTGRES_DB` if you changed them.

4. Set `CIPHERMOTH_VERSION` in `.env` back to the previous version and start it:

   ```shell
   docker compose -f docker-compose.prod.yml up -d backend frontend
   curl -s http://localhost:8000/api/health
   ```

   `/api/health` should show `"schema": "current"`; it also shows `"maintenance": true` until the next step, and until then the rest of the API answers 503.

5. Tell the updater you are done (it hands the command to the running updater). This leaves maintenance mode and allows updates again; it changes no data:

   ```shell
   docker compose -f docker-compose.prod.yml --profile autoupdate exec updater updater.sh resolve
   ```

6. Unlock the vault and check your entries. Then drop the failed database (`ciphermoth_failed_manual`, or the updater's `ciphermoth_failed_<id>`): `docker compose -f docker-compose.prod.yml exec db dropdb -U ciphermoth <name>`.

If the snapshot itself is gone or damaged, restore your last CipherMoth backup ZIP into a fresh vault instead (Settings, "Import").

If the API is stuck in maintenance mode and the updater container no longer exists, recreate it (`docker compose -f docker-compose.prod.yml --profile autoupdate up -d updater`): it finishes or rolls back the interrupted update. Remove `/update-control/maintenance.json` by hand only if you have restored a consistent database yourself.

## Settings

The updater reads these from its `environment` in `docker-compose.prod.yml` (all optional):

| Variable | Default | Meaning |
|---|---|---|
| `COSIGN_IDENTITY_REGEXP`, `COSIGN_OIDC_ISSUER` | CipherMoth's release workflow | Which signatures to trust (forks set their own) |
| `IMAGE_REPO` | `ghcr.io/mr-grj/ciphermoth` | Where the images come from |
| `HEALTH_RETRIES`, `HEALTH_INTERVAL`, `HEALTH_STABLE` | `60`, `3`, `3` | How long a new version may take to become healthy, and for how many checks in a row it must stay so |
| `SNAPSHOT_KEEP` | `3` | Snapshots to keep |
| `ROLLBACK_ATTEMPTS`, `ROLLBACK_RESUMES` | `3`, `10` | Failed rollback attempts, and restarts during a rollback, before asking for help |
| `REQUEST_MAX_AGE` | `900` | Seconds after which an unprocessed request is refused |
| `DEPENDENCY_TIMEOUT` | `600` | Seconds to wait for Docker and the database before recovering after a restart; after that the updater exits and Docker restarts it later |
