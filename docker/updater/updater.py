import fcntl
import hashlib
import json
import os
import re
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
import tomllib
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

PROTOCOL = 2
MIN_PROTOCOL_LABEL = "io.ciphermoth.min-updater-protocol"
SERVICES = ("backend", "frontend")
SNAPSHOT_FORMAT = "ciphermoth-snapshot-v1"

VERSION_RE = re.compile(r"v?(\d{1,9})\.(\d{1,9})\.(\d{1,9})", re.ASCII)
TAG_RE = re.compile(r"v(\d{1,9})\.(\d{1,9})\.(\d{1,9})", re.ASCII)
REQUEST_ID_RE = re.compile(r"[0-9a-f]{32}", re.ASCII)
DATABASE_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,21}", re.ASCII)
DIGEST_SUFFIX_RE = re.compile(r"@sha256:[0-9a-f]{64}", re.ASCII)
ENV_VERSION_LINE = re.compile(rb"^CIPHERMOTH_VERSION=[^\r\n]*", re.MULTILINE)
SCRIPT_SRC_RE = re.compile(rb'<script[^>]*\ssrc="(/assets/[A-Za-z0-9._-]+\.js)"')
MAX_REQUEST_BYTES = 4096
MAX_STATE_BYTES = 1 << 20
REMEMBERED_REQUESTS = 50

ACTIVE = ("preparing", "verifying", "snapshotting", "applying", "validating")
OPERATOR_COMMANDS = ("resolve", "retry")
ROLLING_BACK = "rolling_back"
INTERVENTION = "intervention"
TERMINAL = ("committed", "rolled_back", "failed", "resolved")

RESULT_STATES = {
    "preparing": "verifying",
    "verifying": "verifying",
    "snapshotting": "snapshotting",
    "applying": "applying",
    "validating": "validating",
    ROLLING_BACK: "rolling_back",
    "committed": "success",
    "rolled_back": "rolled_back",
    "failed": "failed",
    "resolved": "failed",
    INTERVENTION: "intervention",
}

PHASE_DETAILS = {
    "preparing": "Checking the running version",
    "verifying": "Verifying image signatures",
    "snapshotting": "Taking a verified database snapshot",
    "applying": "Applying the update",
    "validating": "Checking the new version",
    ROLLING_BACK: "Rolling back to the previous version",
}

RECREATE_UPDATER = (
    "docker compose -f docker-compose.prod.yml --profile autoupdate pull updater && "
    "docker compose -f docker-compose.prod.yml --profile autoupdate up -d "
    "--no-deps updater"
)


class StepError(Exception):
    pass


class Refused(Exception):
    pass


class JournalUnreadable(Exception):
    pass


def log(message: str) -> None:
    print(f"[updater] {message}", file=sys.stderr, flush=True)


def utc_now() -> datetime:
    return datetime.now(UTC)


def timestamp() -> str:
    return utc_now().strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_version(
    value: object, pattern: re.Pattern[str] = VERSION_RE
) -> tuple[int, ...] | None:
    if not isinstance(value, str):
        return None
    match = pattern.fullmatch(value)
    return tuple(int(part) for part in match.groups()) if match else None


def is_newer(candidate: object, current: object) -> bool:
    new = parse_version(candidate)
    old = parse_version(current)
    return new is not None and old is not None and new > old


def plain_version(value: str) -> str:
    return value[1:] if value.startswith("v") else value


def env_version(text: bytes) -> str | None:
    lines = ENV_VERSION_LINE.findall(text)
    if not lines:
        return None
    value = lines[-1].split(b"=", 1)[1].strip().decode("utf-8", "replace")
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    return value


def with_version(text: bytes, tag: str) -> bytes:
    if parse_version(tag) is None or tag.startswith("v"):
        raise ValueError("not an image tag")
    line = f"CIPHERMOTH_VERSION={tag}".encode()
    if ENV_VERSION_LINE.search(text):
        return ENV_VERSION_LINE.sub(lambda _: line, text)
    separator = b"" if not text or text.endswith(b"\n") else b"\n"
    return text + separator + line + b"\n"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fsync_dir(path: Path) -> None:
    with suppress(OSError):
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def write_atomic(
    path: Path,
    data: bytes,
    mode: int = 0o644,
    owner: tuple[int, int] | None = None,
) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "wb") as handle:
            os.fchmod(handle.fileno(), mode)
            if owner is not None:
                with suppress(OSError):
                    os.fchown(handle.fileno(), *owner)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        with suppress(FileNotFoundError):
            os.unlink(tmp)
        raise
    fsync_dir(path.parent)


def write_json(path: Path, payload: dict, mode: int = 0o644) -> None:
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    write_atomic(path, text.encode(), mode)


def read_bounded(path: Path, limit: int = MAX_STATE_BYTES) -> bytes | None:
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        return None
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            return None
        data = os.read(fd, limit + 1)
    finally:
        os.close(fd)
    return data if len(data) <= limit else None


def read_json(path: Path) -> dict | None:
    raw = read_bounded(path)
    if raw is None:
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def quote_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    return int(raw) if raw else default


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    return float(raw) if raw else default


def _updater_version() -> str:
    explicit = os.environ.get("CIPHERMOTH_UPDATER_VERSION", "").strip()
    if explicit:
        return explicit
    path = Path(
        os.environ.get(
            "CIPHERMOTH_UPDATER_VERSION_FILE",
            "/usr/local/share/ciphermoth/pyproject.toml",
        )
    )
    try:
        return tomllib.loads(path.read_text())["project"]["version"]
    except (OSError, KeyError, ValueError):
        return "0.0.0"


@dataclass(frozen=True)
class Settings:
    control_dir: Path
    compose_file: str
    env_file: Path
    backup_dir: Path
    image_repo: str
    identity_regexp: str
    oidc_issuer: str
    backend_url: str
    frontend_url: str
    health_retries: int
    health_interval: float
    health_stable: int
    poll_interval: float
    heartbeat_interval: float
    snapshot_keep: int
    request_max_age: int
    rollback_attempts: int
    rollback_resumes: int
    dependency_timeout: float
    retry_interval: float
    pg_host: str
    pg_port: str
    pg_user: str
    pg_password: str
    pg_database: str
    fault: str
    version: str

    @classmethod
    def from_env(cls) -> "Settings":
        get = os.environ.get
        return cls(
            control_dir=Path(get("UPDATE_CONTROL_DIR", "/update-control")),
            compose_file=get("COMPOSE_FILE", "/work/docker-compose.prod.yml"),
            env_file=Path(get("ENV_FILE", "/work/.env")),
            backup_dir=Path(get("BACKUP_DIR", "/backups")),
            image_repo=get("IMAGE_REPO", "ghcr.io/mr-grj/ciphermoth"),
            identity_regexp=get(
                "COSIGN_IDENTITY_REGEXP",
                r"^https://github.com/mr-grj/ciphermoth/\.github/workflows/"
                r"release\.yml@refs/tags/v.*",
            ),
            oidc_issuer=get(
                "COSIGN_OIDC_ISSUER", "https://token.actions.githubusercontent.com"
            ),
            backend_url=get("BACKEND_URL", "http://backend:80").rstrip("/"),
            frontend_url=get("FRONTEND_URL", "http://frontend:3000").rstrip("/"),
            health_retries=_env_int("HEALTH_RETRIES", 60),
            health_interval=_env_float("HEALTH_INTERVAL", 3),
            health_stable=max(1, _env_int("HEALTH_STABLE", 3)),
            poll_interval=_env_float("POLL_INTERVAL", 5),
            heartbeat_interval=_env_float("HEARTBEAT_INTERVAL", 10),
            snapshot_keep=max(1, _env_int("SNAPSHOT_KEEP", 3)),
            request_max_age=_env_int("REQUEST_MAX_AGE", 900),
            rollback_attempts=max(1, _env_int("ROLLBACK_ATTEMPTS", 3)),
            rollback_resumes=max(1, _env_int("ROLLBACK_RESUMES", 10)),
            dependency_timeout=_env_float("DEPENDENCY_TIMEOUT", 600),
            retry_interval=_env_float("RETRY_INTERVAL", 5),
            pg_host=get("POSTGRES_HOST", "db"),
            pg_port=get("POSTGRES_PORT", "5432"),
            pg_user=get("POSTGRES_USER", "ciphermoth"),
            pg_password=get("POSTGRES_PASSWORD", ""),
            pg_database=get("POSTGRES_DB", "ciphermoth"),
            fault=get("CIPHERMOTH_UPDATER_FAULT", ""),
            version=_updater_version(),
        )


class Runner:
    def __init__(self, secrets: tuple[str, ...] = ()) -> None:
        self.secrets = tuple(secret for secret in secrets if secret)

    def redact(self, text: str) -> str:
        for secret in self.secrets:
            text = text.replace(secret, "[redacted]")
        return text

    def run(
        self,
        args: list[str],
        *,
        timeout: float = 600,
        check: bool = True,
        env: dict[str, str] | None = None,
        what: str | None = None,
    ) -> subprocess.CompletedProcess[bytes]:
        label = what or " ".join(args[:3])
        try:
            proc = subprocess.run(
                args,
                capture_output=True,
                timeout=timeout,
                env=env,
                stdin=subprocess.DEVNULL,
            )
        except subprocess.TimeoutExpired as error:
            raise StepError(f"{label} timed out") from error
        except FileNotFoundError as error:
            raise StepError(f"{args[0]} is not installed") from error
        if check and proc.returncode != 0:
            detail = self.redact(proc.stderr.decode("utf-8", "replace").strip())
            log(f"{label} failed with exit code {proc.returncode}: {detail[-2000:]}")
            raise StepError(f"{label} failed")
        return proc


class Docker:
    def __init__(self, settings: Settings, runner: Runner) -> None:
        self.settings = settings
        self.runner = runner

    def compose(
        self,
        *args: str,
        env_file: Path | None = None,
        timeout: float = 600,
        check: bool = True,
    ) -> subprocess.CompletedProcess[bytes]:
        command = [
            "docker",
            "compose",
            "-f",
            self.settings.compose_file,
            "--env-file",
            str(env_file or self.settings.env_file),
            *args,
        ]
        return self.runner.run(
            command, timeout=timeout, check=check, what=f"docker compose {args[0]}"
        )

    def _inspect(self, kind: str, ref: str) -> dict | None:
        proc = self.runner.run(
            ["docker", kind, "inspect", ref],
            check=False,
            timeout=60,
            what=f"docker {kind} inspect",
        )
        if proc.returncode != 0:
            return None
        try:
            data = json.loads(proc.stdout)
        except ValueError:
            return None
        return data[0] if isinstance(data, list) and data else None

    def image(self, ref: str) -> dict | None:
        return self._inspect("image", ref)

    def container(self, service: str) -> dict | None:
        proc = self.compose("ps", "-a", "-q", service, check=False, timeout=60)
        ids = proc.stdout.decode().split() if proc.returncode == 0 else []
        return self._inspect("container", ids[0]) if ids else None

    def pull(self, ref: str) -> None:
        self.runner.run(["docker", "pull", ref], timeout=1800, what=f"pull {ref}")

    def tag(self, source: str, target: str) -> None:
        self.runner.run(["docker", "tag", source, target], timeout=60, what="tag")

    def service_images(self, env_file: Path) -> dict[str, str]:
        proc = self.compose(
            "config", "--format", "json", env_file=env_file, timeout=120
        )
        try:
            services = json.loads(proc.stdout)["services"]
            return {name: services[name]["image"] for name in SERVICES}
        except (ValueError, KeyError, TypeError) as error:
            raise StepError("could not read the compose configuration") from error


def is_running(container: dict | None) -> bool:
    state = (container or {}).get("State") or {}
    return bool(state.get("Running")) and not state.get("Restarting")


class Postgres:
    def __init__(self, settings: Settings, runner: Runner, passfile: Path) -> None:
        self.settings = settings
        self.runner = runner
        self.passfile = passfile
        self.env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("PG") and key != "POSTGRES_PASSWORD"
        }
        self.env.update(
            {
                "PGHOST": settings.pg_host,
                "PGPORT": settings.pg_port,
                "PGUSER": settings.pg_user,
                "PGPASSFILE": str(passfile),
                "PGCONNECT_TIMEOUT": "10",
                "PGAPPNAME": "ciphermoth-updater",
            }
        )

    def write_passfile(self) -> None:
        escaped = self.settings.pg_password.replace("\\", "\\\\").replace(":", "\\:")
        user = self.settings.pg_user.replace("\\", "\\\\").replace(":", "\\:")
        self.passfile.parent.mkdir(parents=True, exist_ok=True)
        write_atomic(self.passfile, f"*:*:*:{user}:{escaped}\n".encode(), mode=0o600)

    def query(self, sql: str, database: str = "postgres", timeout: float = 600) -> list:
        proc = self.runner.run(
            [
                "psql",
                "-X",
                "-q",
                "-w",
                "-A",
                "-t",
                "-F",
                "\t",
                "-v",
                "ON_ERROR_STOP=1",
                "-d",
                database,
                "-c",
                sql,
            ],
            env=self.env,
            timeout=timeout,
            what="psql",
        )
        lines = proc.stdout.decode("utf-8", "replace").splitlines()
        return [line.split("\t") for line in lines if line]

    def exists(self, database: str) -> bool:
        rows = self.query(
            f"SELECT 1 FROM pg_database WHERE datname = {quote_literal(database)}"
        )
        return bool(rows)

    def list_databases(self) -> list[str]:
        return [row[0] for row in self.query("SELECT datname FROM pg_database")]

    def size(self, database: str) -> int:
        rows = self.query(f"SELECT pg_database_size({quote_literal(database)})")
        return int(rows[0][0])

    def terminate(self, *databases: str) -> None:
        names = ", ".join(quote_literal(name) for name in databases)
        self.query(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            f"WHERE datname IN ({names}) AND pid <> pg_backend_pid()"
        )

    def other_connections(self, database: str) -> int:
        rows = self.query(
            "SELECT count(*) FROM pg_stat_activity "
            f"WHERE datname = {quote_literal(database)} AND pid <> pg_backend_pid()"
        )
        return int(rows[0][0])

    def create(self, database: str) -> None:
        self.query(f"CREATE DATABASE {quote_ident(database)}")

    def drop(self, database: str) -> None:
        self.query(f"DROP DATABASE IF EXISTS {quote_ident(database)} WITH (FORCE)")

    def swap(self, live: str, replacement: str, retired: str) -> None:
        sql = swap_sql(live, replacement, retired, self.exists(live))
        for attempt in range(5):
            self.terminate(live, replacement)
            try:
                self.query(sql)
                return
            except StepError:
                if attempt == 4:
                    raise
                time.sleep(1)

    def dump(self, database: str, path: Path) -> None:
        self.runner.run(
            ["pg_dump", "-w", "-Fc", "-d", database, "-f", str(path)],
            env=self.env,
            timeout=3600,
            what="pg_dump",
        )

    def check_archive(self, path: Path) -> None:
        self.runner.run(
            ["pg_restore", "--list", str(path)],
            env=self.env,
            timeout=600,
            what="pg_restore --list",
        )

    def restore(self, path: Path, database: str) -> None:
        self.runner.run(
            [
                "pg_restore",
                "-w",
                "--exit-on-error",
                "--single-transaction",
                "-d",
                database,
                str(path),
            ],
            env=self.env,
            timeout=3600,
            what="pg_restore",
        )

    def fingerprint(self, database: str) -> dict:
        user_schemas = "NOT IN ('pg_catalog', 'information_schema')"
        tables = [
            row[0]
            for row in self.query(
                "SELECT quote_ident(schemaname) || '.' || quote_ident(tablename) "
                f"FROM pg_tables WHERE schemaname {user_schemas} ORDER BY 1",
                database,
            )
        ]
        counts: dict[str, dict] = {}
        if tables:
            parts = [
                f"SELECT {index}, count(*), "
                "coalesce(md5(string_agg(h, ',' ORDER BY h)), '') "
                f"FROM (SELECT md5(r::text) AS h FROM {table} r) s"
                for index, table in enumerate(tables)
            ]
            for index, rows, digest in self.query(
                " UNION ALL ".join(parts) + " ORDER BY 1", database, timeout=3600
            ):
                counts[tables[int(index)]] = {"rows": int(rows), "md5": digest}
        sequences = {
            name: value
            for name, value in self.query(
                "SELECT quote_ident(schemaname) || '.' || quote_ident(sequencename), "
                "coalesce(last_value::text, '-') FROM pg_sequences "
                f"WHERE schemaname {user_schemas} ORDER BY 1",
                database,
            )
        }
        schema = self.query(
            "SELECT md5(coalesce(string_agg(x, E'\\n' ORDER BY x), '')) FROM ("
            "SELECT format('col %s.%s.%s %s %s %s', table_schema, table_name, "
            "column_name, data_type, is_nullable, coalesce(column_default, '')) x "
            f"FROM information_schema.columns WHERE table_schema {user_schemas} "
            "UNION ALL SELECT format('idx %s.%s %s', schemaname, indexname, indexdef) "
            f"FROM pg_indexes WHERE schemaname {user_schemas} "
            "UNION ALL SELECT format('con %s %s', conname, pg_get_constraintdef(oid)) "
            "FROM pg_constraint WHERE connamespace NOT IN "
            "('pg_catalog'::regnamespace, 'information_schema'::regnamespace)) s",
            database,
        )[0][0]
        alembic: list[str] = []
        if "public.alembic_version" in counts:
            alembic = sorted(
                row[0]
                for row in self.query(
                    "SELECT version_num FROM public.alembic_version", database
                )
            )
        return {
            "tables": counts,
            "sequences": sequences,
            "schema": schema,
            "alembic": alembic,
        }

    def server_version(self) -> str:
        return self.query("SHOW server_version")[0][0]


def swap_sql(live: str, replacement: str, retired: str, live_exists: bool) -> str:
    statements = []
    if live_exists:
        statements.append(
            f"ALTER DATABASE {quote_ident(live)} RENAME TO {quote_ident(retired)}"
        )
    statements.append(
        f"ALTER DATABASE {quote_ident(replacement)} RENAME TO {quote_ident(live)}"
    )
    return "BEGIN; " + "; ".join(statements) + "; COMMIT;"


class Snapshots:
    def __init__(self, directory: Path) -> None:
        self.dir = directory

    def dump_path(self, name: str) -> Path:
        return self.dir / f"{name}.dump"

    def manifest_path(self, name: str) -> Path:
        return self.dir / f"{name}.json"

    def partial_path(self, name: str) -> Path:
        return self.dir / f"{name}.dump.partial"

    def verified(self, name: str) -> dict | None:
        manifest = read_json(self.manifest_path(name))
        dump = self.dump_path(name)
        if (
            manifest is None
            or manifest.get("format") != SNAPSHOT_FORMAT
            or manifest.get("name") != name
            or not dump.is_file()
            or dump.stat().st_size != manifest.get("size")
            or sha256_file(dump) != manifest.get("sha256")
        ):
            return None
        return manifest

    def names(self) -> list[str]:
        return sorted(
            path.name[: -len(".json")]
            for path in self.dir.glob("*.json")
            if not path.name.startswith(".")
        )

    def discard(self, name: str) -> None:
        for path in (
            self.partial_path(name),
            self.dump_path(name),
            self.manifest_path(name),
        ):
            with suppress(FileNotFoundError):
                path.unlink()

    def prune(self, keep: int, protect: set[str]) -> None:
        names = self.names()
        complete = [name for name in names if self.dump_path(name).is_file()]
        for name in names:
            if name not in complete and name not in protect:
                self.discard(name)
        for name in complete[:-keep] if keep else complete:
            if name not in protect:
                log(f"removing old snapshot {name}")
                self.discard(name)
        for partial in self.dir.glob("*.dump.partial"):
            name = partial.name[: -len(".dump.partial")]
            if name not in protect:
                with suppress(FileNotFoundError):
                    partial.unlink()


class Journal:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> dict | None:
        try:
            raw = self.path.read_bytes()
        except FileNotFoundError:
            return None
        except OSError as error:
            raise JournalUnreadable(str(error)) from error
        try:
            data = json.loads(raw)
        except ValueError as error:
            raise JournalUnreadable("the update journal is not valid JSON") from error
        if not isinstance(data, dict) or not isinstance(data.get("phase"), str):
            raise JournalUnreadable("the update journal has no phase")
        if data.get("protocol") != PROTOCOL:
            raise JournalUnreadable(
                f"the update journal uses protocol {data.get('protocol')}, "
                f"this updater speaks {PROTOCOL}"
            )
        return data

    def save(self, data: dict) -> None:
        write_json(self.path, data, mode=0o600)


@dataclass
class Request:
    id: str
    target: str
    requested_at: datetime | None


def parse_request(raw: bytes, max_age: int, now: datetime | None = None) -> Request:
    if len(raw) > MAX_REQUEST_BYTES:
        raise Refused("the update request is too large")
    try:
        data = json.loads(raw)
    except ValueError as error:
        raise Refused("the update request is not valid JSON") from error
    if not isinstance(data, dict):
        raise Refused("the update request is not a JSON object")
    target = data.get("target")
    if not isinstance(target, str) or parse_version(target, TAG_RE) is None:
        raise Refused("the requested target is not a release tag")
    request_id = data.get("id")
    if request_id is None:
        request_id = uuid.uuid4().hex
    elif not isinstance(request_id, str) or not REQUEST_ID_RE.fullmatch(request_id):
        raise Refused("the update request has an invalid id")
    requested_at = None
    raw_time = data.get("requested_at")
    if raw_time is not None:
        if not isinstance(raw_time, str):
            raise Refused("the update request has an invalid time")
        try:
            requested_at = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
        except ValueError as error:
            raise Refused("the update request has an invalid time") from error
        if requested_at.tzinfo is None:
            requested_at = requested_at.replace(tzinfo=UTC)
        age = ((now or utc_now()) - requested_at).total_seconds()
        if age > max_age:
            raise Refused("the update request expired before the updater saw it")
        if age < -300:
            raise Refused("the update request is dated in the future")
    return Request(id=request_id, target=target, requested_at=requested_at)


class Control:
    def __init__(self, directory: Path) -> None:
        self.dir = directory
        self.request = directory / "request.json"
        self.result = directory / "result.json"
        self.heartbeat = directory / "updater.json"
        self.maintenance = directory / "maintenance.json"
        self.ready = directory / "updater.ready"
        self.stuck_request = False

    def has_request(self) -> bool:
        return os.path.lexists(self.request)

    def take_request(self) -> bytes | None:
        if not self.has_request():
            return None
        data = b""
        try:
            fd = os.open(self.request, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except FileNotFoundError:
            return None
        except OSError:
            log("ignoring a request file that is not a regular file")
        else:
            try:
                if stat.S_ISREG(os.fstat(fd).st_mode):
                    data = os.read(fd, MAX_REQUEST_BYTES + 1)
            finally:
                os.close(fd)
        try:
            os.unlink(self.request)
        except FileNotFoundError:
            pass
        except OSError as error:
            if not self.stuck_request:
                log(f"cannot remove the request file ({error}); ignoring it")
            self.stuck_request = True
            return None
        self.stuck_request = False
        return data

    def publish(self, payload: dict) -> None:
        write_json(self.result, payload)

    def maintenance_on(self, payload: dict) -> None:
        write_json(self.maintenance, payload)

    def maintenance_owner(self) -> str | None:
        data = read_json(self.maintenance)
        return data.get("id") if data else None

    def maintenance_off(self, update_id: str) -> None:
        if not os.path.lexists(self.maintenance):
            return
        owner = self.maintenance_owner()
        if owner not in (None, update_id):
            log(f"leaving maintenance mode owned by update {owner}")
            return
        with suppress(FileNotFoundError):
            os.unlink(self.maintenance)
        fsync_dir(self.dir)


class Heartbeat:
    def __init__(self, control: Control, settings: Settings) -> None:
        self.control = control
        self.settings = settings
        self.lock = threading.Lock()
        self.started_at = timestamp()
        self.busy = False
        self.phase: str | None = None
        self.update_id: str | None = None
        self.stopping = threading.Event()
        self.thread: threading.Thread | None = None

    def set(self, phase: str | None, update_id: str | None, busy: bool) -> None:
        with self.lock:
            self.phase, self.update_id, self.busy = phase, update_id, busy
        self.beat()

    def beat(self, running: bool = True) -> None:
        with self.lock:
            payload = {
                "protocol": PROTOCOL,
                "version": self.settings.version,
                "started_at": self.started_at,
                "heartbeat_at": timestamp(),
                "running": running,
                "busy": self.busy,
                "phase": self.phase,
                "update_id": self.update_id,
            }
        try:
            write_json(self.control.heartbeat, payload)
        except OSError as error:
            log(f"could not write the heartbeat: {error}")

    def start(self) -> None:
        def loop() -> None:
            while not self.stopping.wait(self.settings.heartbeat_interval):
                self.beat()

        self.beat()
        self.thread = threading.Thread(target=loop, name="heartbeat", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stopping.set()
        self.beat(running=False)


class Updater:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.state_dir = settings.backup_dir / "state"
        self.updates_dir = self.state_dir / "updates"
        self.snapshots = Snapshots(settings.backup_dir / "snapshots")
        self.journal = Journal(self.state_dir / "journal.json")
        self.control = Control(settings.control_dir)
        self.runner = Runner((settings.pg_password,))
        self.docker = Docker(settings, self.runner)
        self.pg = Postgres(
            settings,
            self.runner,
            Path(os.environ.get("PGPASS_PATH", "/tmp/ciphermoth-updater.pgpass")),
        )
        self.heartbeat = Heartbeat(self.control, settings)
        self.sleep: Callable[[float], None] = time.sleep

    def setup(self) -> None:
        if not DATABASE_RE.fullmatch(self.settings.pg_database):
            raise SystemExit(
                "POSTGRES_DB must be a plain identifier of at most 22 characters"
            )
        for directory in (self.state_dir, self.updates_dir, self.snapshots.dir):
            directory.mkdir(parents=True, exist_ok=True)
            os.chmod(directory, 0o700)
        os.chmod(self.settings.backup_dir, 0o700)
        self.control.dir.mkdir(parents=True, exist_ok=True)
        self.pg.write_passfile()

    @contextmanager
    def locked(self) -> Iterator[None]:
        handle = (self.state_dir / "lock").open("a+")
        try:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                log("another updater holds the lock; waiting for it to finish")
                fcntl.flock(handle, fcntl.LOCK_EX)
            yield
        finally:
            handle.close()

    def fault(self, point: str) -> None:
        for item in filter(None, self.settings.fault.split(",")):
            action, _, where = item.strip().partition(":")
            if where != point:
                continue
            marker = self.state_dir / f"fault-{action}-{point}.fired"
            if marker.exists():
                continue
            marker.touch()
            log(f"fault injection: {action} at {point}")
            if action == "kill":
                os.kill(os.getpid(), signal.SIGKILL)
            if action == "fail":
                raise StepError(f"fault injected at {point}")

    def corrupt_requested(self, point: str) -> bool:
        return f"corrupt:{point}" in self.settings.fault.split(",")

    def publish(self, state: str, detail: str, target: str | None, **extra) -> None:
        payload = {
            "state": state,
            "detail": detail,
            "target": target or "",
            "finished_at": timestamp(),
            "protocol": PROTOCOL,
            "updater_version": self.settings.version,
            **extra,
        }
        self.control.publish(payload)

    def refuse(
        self, target: str | None, reason: str, request_id: str | None = None
    ) -> None:
        log(f"refused: {reason}")
        extra = {"id": request_id} if request_id else {}
        self.publish(
            "failed", f"Refused: {reason}. Nothing was changed.", target, **extra
        )

    def refuse_request(self, request: Request, reason: str) -> None:
        self.refuse(request.target, reason, request.id)

    def transition(self, journal: dict, phase: str, detail: str | None = None) -> None:
        journal["phase"] = phase
        journal.setdefault("history", []).append({"phase": phase, "at": timestamp()})
        if detail is not None:
            journal["detail"] = detail
        self.journal.save(journal)
        busy = phase in ACTIVE or phase == ROLLING_BACK
        self.heartbeat.set(phase, journal["id"], busy)
        self.publish(
            RESULT_STATES[phase],
            detail or PHASE_DETAILS.get(phase, phase),
            f"v{journal['target']}",
            phase=phase,
            id=journal["id"],
            previous=journal["previous"].get("version"),
            snapshot=(journal.get("snapshot") or {}).get("name"),
        )
        log(f"update {journal['id'][:12]}: {phase}")

    def running_version(self) -> str | None:
        data = self.http_json(f"{self.settings.backend_url}/api/meta")
        version = data.get("version") if data else None
        return version if isinstance(version, str) else None

    def http(self, url: str) -> tuple[int, dict[str, str], bytes] | None:
        proc = self.runner.run(
            ["curl", "-sS", "-i", "--max-time", "5", url],
            check=False,
            timeout=15,
            what="curl",
        )
        if proc.returncode != 0:
            return None
        head, _, body = proc.stdout.partition(b"\r\n\r\n")
        lines = head.decode("latin-1").split("\r\n")
        try:
            status = int(lines[0].split()[1])
        except (IndexError, ValueError):
            return None
        headers = {}
        for line in lines[1:]:
            name, _, value = line.partition(":")
            headers[name.strip().lower()] = value.strip()
        return status, headers, body

    def http_json(self, url: str) -> dict | None:
        response = self.http(url)
        if response is None or response[0] != 200:
            return None
        try:
            data = json.loads(response[2])
        except ValueError:
            return None
        return data if isinstance(data, dict) else None

    def health_problem(self, version: str, images: dict) -> str | None:
        for service in SERVICES:
            if not is_running(self.docker.container(service)):
                return f"the {service} container is not running"
        backend = self.settings.backend_url
        meta = self.http_json(f"{backend}/api/meta")
        if meta is None:
            return "the backend does not answer"
        if plain_version(str(meta.get("version", ""))) != version:
            return f"the backend reports version {meta.get('version')}"
        if images["backend"].get("protocol_aware"):
            health = self.http_json(f"{backend}/api/health")
            if health is None:
                return "the backend health check does not answer"
            if health.get("schema") != "current":
                return "the database schema is not at the release's revision"
            if health.get("status") != "ok" or health.get("version") != version:
                return "the backend reports itself unhealthy"
        return self.frontend_problem(version, images["frontend"])

    def frontend_problem(self, version: str, image: dict) -> str | None:
        frontend = self.settings.frontend_url
        index = self.http(f"{frontend}/")
        if index is None or index[0] != 200:
            return "the web UI does not answer"
        status, headers, body = index
        if b"CipherMoth cannot start" in body:
            return "the web UI refused its configuration (check CIPHERMOTH_API_URL)"
        if b'id="root"' not in body or "content-security-policy" not in headers:
            return "the web UI does not serve the application"
        script = SCRIPT_SRC_RE.search(body)
        if script is None:
            return "the web UI page has no application script"
        asset = self.http(f"{frontend}{script.group(1).decode()}")
        if asset is None or asset[0] != 200:
            return "the web UI application script does not load"
        if b"__CIPHERMOTH_API_URL__" in asset[2]:
            return "the web UI was not configured with an API URL"
        if image.get("protocol_aware"):
            info = self.http_json(f"{frontend}/version.json")
            if info is None:
                return "the web UI does not serve its version"
            if info.get("version") != version:
                return f"the web UI reports version {info.get('version')}"
        return None

    def wait_healthy(self, version: str, images: dict) -> None:
        settings = self.settings
        passes = 0
        restarts: tuple | None = None
        problem = "no answer yet"
        for attempt in range(settings.health_retries + settings.health_stable):
            if attempt:
                self.sleep(settings.health_interval)
            found = self.health_problem(version, images)
            if found is not None:
                problem, passes, restarts = found, 0, None
                continue
            counts = tuple(
                (self.docker.container(service) or {}).get("RestartCount")
                for service in SERVICES
            )
            passes = passes + 1 if restarts in (None, counts) else 1
            restarts = counts
            if passes >= settings.health_stable:
                return
        raise StepError(f"health check failed: {problem}")

    def require_stopped(self, *services: str) -> None:
        for service in services:
            if is_running(self.docker.container(service)):
                raise StepError(f"the {service} container is still running")

    def update_dir(self, journal: dict) -> Path:
        return self.updates_dir / journal["id"]

    def short_id(self, journal: dict) -> str:
        return journal["id"][:12]

    def database_names(self, journal: dict) -> tuple[str, str, str]:
        base = self.settings.pg_database
        short = journal["id"]
        return (
            f"{base}_verify_{short}",
            f"{base}_restore_{short}",
            (f"{base}_failed_{short}"),
        )

    def remembered_requests(self) -> list[str]:
        data = read_json(self.state_dir / "requests.json") or {}
        ids = data.get("ids")
        return [i for i in ids if isinstance(i, str)] if isinstance(ids, list) else []

    def remember_request(self, request_id: str) -> None:
        ids = [*self.remembered_requests(), request_id][-REMEMBERED_REQUESTS:]
        write_json(self.state_dir / "requests.json", {"ids": ids}, mode=0o600)

    def read_env(self) -> bytes:
        try:
            return self.settings.env_file.read_bytes()
        except OSError as error:
            raise StepError("could not read the .env file") from error

    def write_env(self, data: bytes, journal: dict) -> None:
        previous = journal["previous"]
        owner = (previous["env_uid"], previous["env_gid"])
        write_atomic(
            self.settings.env_file, data, mode=previous["env_mode"], owner=owner
        )

    def handle_request(self) -> None:
        raw = self.control.take_request()
        if raw is None:
            return
        try:
            request = parse_request(raw, self.settings.request_max_age)
        except Refused as error:
            self.refuse(None, str(error))
            return
        try:
            self.consider(request)
        except StepError as error:
            self.refuse_request(request, str(error))

    def consider(self, request: Request) -> None:
        try:
            current = self.journal.load()
        except JournalUnreadable as error:
            self.refuse_request(request, f"the update journal is unreadable ({error})")
            return
        if current is not None and current["phase"] == INTERVENTION:
            self.refuse_request(
                request,
                "a previous update needs manual attention first (see the "
                "updater logs and docs/UPDATING.md)",
            )
            return
        if current is not None and current["phase"] not in TERMINAL:
            self.refuse_request(request, "another update is still in progress")
            return
        if request.id in self.remembered_requests():
            self.refuse_request(request, "this update request was already handled")
            return
        self.remember_request(request.id)
        running = self.running_version()
        if running is None:
            self.refuse_request(request, "CipherMoth's backend is not answering")
            return
        if not is_newer(request.target, running):
            self.refuse_request(
                request,
                f"{request.target} is not newer than the running version {running}",
            )
            return
        configured = env_version(self.read_env())
        if parse_version(configured) is not None and parse_version(
            configured
        ) != parse_version(running):
            self.refuse_request(
                request,
                f"the .env file names version {configured} but {running} is running",
            )
            return
        journal = {
            "protocol": PROTOCOL,
            "id": request.id,
            "target": plain_version(request.target),
            "created_at": timestamp(),
            "updater_version": self.settings.version,
            "phase": "preparing",
            "history": [],
            "previous": {"version": plain_version(running)},
            "rollback": {"attempts": 0, "swapped": False},
        }
        log(f"update requested: {running} -> {request.target}")
        self.execute(journal)

    def execute(self, journal: dict) -> None:
        self.transition(journal, "preparing")
        try:
            self.prepare(journal)
            self.verify(journal)
            self.take_snapshot(journal)
        except (StepError, Refused) as error:
            self.abort(journal, str(error))
            return
        try:
            self.apply(journal)
            self.validate(journal)
        except StepError as error:
            self.rollback(journal, str(error))
            return
        self.commit(journal)

    def prepare(self, journal: dict) -> None:
        env = self.read_env()
        directory = self.update_dir(journal)
        directory.mkdir(parents=True, exist_ok=True)
        os.chmod(directory, 0o700)
        write_atomic(directory / "env.before", env, mode=0o600)
        info = os.stat(self.settings.env_file)
        previous = journal["previous"]
        previous.update(
            {
                "env_sha256": hashlib.sha256(env).hexdigest(),
                "env_version": env_version(env),
                "env_mode": stat.S_IMODE(info.st_mode),
                "env_uid": info.st_uid,
                "env_gid": info.st_gid,
                "images": {},
            }
        )
        for service in SERVICES:
            container = self.docker.container(service)
            if not is_running(container):
                raise Refused(f"the {service} container is not running")
            assert container is not None
            image = self.docker.image(container["Image"]) or {}
            labels = (image.get("Config") or {}).get("Labels") or {}
            previous["images"][service] = {
                "id": container["Image"],
                "ref": container["Config"]["Image"],
                "protocol_aware": MIN_PROTOCOL_LABEL in labels,
            }
        self.journal.save(journal)
        problem = self.health_problem(previous["version"], previous["images"])
        if problem is not None:
            raise Refused(
                f"CipherMoth is not fully healthy before the update: {problem}"
            )
        configured = self.docker.service_images(directory / "env.before")
        for service in SERVICES:
            if configured[service] != previous["images"][service]["ref"]:
                raise Refused(
                    f"the running {service} image does not match the compose "
                    "configuration; run `docker compose up -d` first"
                )

    def signed_digest(self, image: dict, service: str) -> str:
        repository = f"{self.settings.image_repo}-{service}"
        for digest in image.get("RepoDigests") or []:
            if (
                isinstance(digest, str)
                and digest.startswith(repository + "@")
                and DIGEST_SUFFIX_RE.fullmatch(digest[len(repository) :])
            ):
                return digest
        raise Refused(
            f"the {service} image has no digest from {repository}, so its signature "
            "cannot be verified"
        )

    def verify_signature(self, digest: str) -> None:
        self.runner.run(
            [
                "cosign",
                "verify",
                "--certificate-identity-regexp",
                self.settings.identity_regexp,
                "--certificate-oidc-issuer",
                self.settings.oidc_issuer,
                digest,
            ],
            timeout=300,
            what=f"cosign verify {digest}",
        )
        log(f"signature verified: {digest}")

    def verify(self, journal: dict) -> None:
        self.transition(journal, "verifying")
        target = journal["target"]
        verified = {}
        for service in SERVICES:
            ref = f"{self.settings.image_repo}-{service}:{target}"
            try:
                self.docker.pull(ref)
            except StepError as error:
                raise StepError(f"could not pull the {service} image") from error
            image = self.docker.image(ref)
            if image is None:
                raise StepError(f"the {service} image is missing after the pull")
            digest = self.signed_digest(image, service)
            try:
                self.verify_signature(digest)
            except StepError as error:
                raise StepError(
                    f"the {service} image signature could not be verified"
                ) from error
            labels = (image.get("Config") or {}).get("Labels") or {}
            required = labels.get(MIN_PROTOCOL_LABEL) or "1"
            if not required.isdigit() or int(required) > PROTOCOL:
                raise Refused(
                    f"v{target} needs updater protocol {required}, this updater "
                    f"speaks {PROTOCOL}; update the updater first: {RECREATE_UPDATER}"
                )
            verified[service] = {
                "ref": ref,
                "id": image["Id"],
                "digest": digest,
                "protocol_aware": MIN_PROTOCOL_LABEL in labels,
            }
        for service in SERVICES:
            previous = journal["previous"]["images"][service]
            image = self.docker.image(previous["id"])
            if image is None:
                raise Refused(f"the running {service} image is missing")
            previous["digest"] = self.signed_digest(image, service)
            try:
                self.verify_signature(previous["digest"])
            except StepError as error:
                raise StepError(
                    f"the running {service} image (the rollback target) is not "
                    "a verified release"
                ) from error
        candidate = self.update_dir(journal) / "env.target"
        before = (self.update_dir(journal) / "env.before").read_bytes()
        write_atomic(candidate, with_version(before, target), mode=0o600)
        configured = self.docker.service_images(candidate)
        for service in SERVICES:
            if configured[service] != verified[service]["ref"]:
                raise Refused(
                    f"the compose file does not run {verified[service]['ref']} for "
                    f"{service} (it names {configured[service]})"
                )
        journal["target_images"] = verified
        self.journal.save(journal)
        self.fault("verified")

    def maintenance_on(self, journal: dict, snapshot_verified: bool) -> None:
        self.control.maintenance_on(
            {
                "protocol": PROTOCOL,
                "id": journal["id"],
                "target": journal["target"],
                "previous": journal["previous"]["version"],
                "snapshot_verified": snapshot_verified,
                "since": timestamp(),
            }
        )

    def take_snapshot(self, journal: dict) -> None:
        self.transition(journal, "snapshotting")
        journal["quiesced"] = True
        self.journal.save(journal)
        self.maintenance_on(journal, snapshot_verified=False)
        self.fault("maintenance_on")
        self.docker.compose("stop", "backend", timeout=180)
        self.require_stopped("backend")
        self.fault("backend_stopped")
        self.pg.terminate(self.settings.pg_database)
        name = f"{utc_now().strftime('%Y%m%dT%H%M%S%fZ')}-{self.short_id(journal)}"
        journal["snapshot"] = {"name": name, "state": "creating"}
        self.journal.save(journal)
        manifest = self.create_snapshot(journal, name)
        journal["snapshot"] = {
            "name": name,
            "state": "verified",
            "sha256": manifest["sha256"],
            "created_at": manifest["created_at"],
        }
        self.journal.save(journal)
        self.maintenance_on(journal, snapshot_verified=True)
        self.fault("snapshot_committed")

    def create_snapshot(self, journal: dict, name: str) -> dict:
        database = self.settings.pg_database
        verify_db, _, _ = self.database_names(journal)
        partial = self.snapshots.partial_path(name)
        size = self.pg.size(database)
        free = os.statvfs(self.snapshots.dir)
        if free.f_bavail * free.f_frsize < 2 * size + 64 * 1024 * 1024:
            raise StepError("not enough free disk space for the database snapshot")
        log(f"snapshotting {database} ({size} bytes)")
        self.pg.dump(database, partial)
        with partial.open("rb+") as handle:
            if self.corrupt_requested("snapshot"):
                handle.truncate(max(1, partial.stat().st_size // 2))
            os.fsync(handle.fileno())
        os.chmod(partial, 0o600)
        self.fault("snapshot_dumped")
        try:
            self.pg.check_archive(partial)
        except StepError as error:
            raise StepError(
                "the database snapshot is not a readable archive"
            ) from error
        live = self.pg.fingerprint(database)
        self.pg.drop(verify_db)
        try:
            self.pg.create(verify_db)
            try:
                self.pg.restore(partial, verify_db)
            except StepError as error:
                raise StepError("the database snapshot does not restore") from error
            restored = self.pg.fingerprint(verify_db)
        finally:
            self.pg.drop(verify_db)
        if restored != live:
            raise StepError("the restored snapshot differs from the database")
        self.fault("snapshot_verified")
        manifest = {
            "format": SNAPSHOT_FORMAT,
            "name": name,
            "file": f"{name}.dump",
            "sha256": sha256_file(partial),
            "size": partial.stat().st_size,
            "created_at": timestamp(),
            "database": database,
            "server_version": self.pg.server_version(),
            "app_version": journal["previous"]["version"],
            "update_id": journal["id"],
            "fingerprint": live,
        }
        write_json(self.snapshots.manifest_path(name), manifest, mode=0o600)
        os.replace(partial, self.snapshots.dump_path(name))
        fsync_dir(self.snapshots.dir)
        if self.snapshots.verified(name) is None:
            raise StepError("the committed snapshot does not match its manifest")
        log(f"snapshot {name} verified ({manifest['size']} bytes)")
        return manifest

    def apply(self, journal: dict) -> None:
        journal["applied"] = True
        self.transition(journal, "applying")
        target = (self.update_dir(journal) / "env.target").read_bytes()
        self.write_env(target, journal)
        self.fault("env_written")
        for service, image in journal["target_images"].items():
            current = self.docker.image(image["ref"])
            if current is None or current.get("Id") != image["id"]:
                raise StepError(f"the {service} image changed after verification")
        self.docker.compose("up", "-d", *SERVICES, timeout=900)
        self.fault("compose_up_done")
        for service, image in journal["target_images"].items():
            container = self.docker.container(service)
            if container is None or container.get("Image") != image["id"]:
                raise StepError(
                    f"the {service} container does not run the verified image"
                )

    def validate(self, journal: dict) -> None:
        self.transition(journal, "validating")
        self.wait_healthy(journal["target"], journal["target_images"])
        self.fault("validated")

    def commit(self, journal: dict) -> None:
        self.transition(
            journal, "committed", detail=f"Updated to v{journal['target']}."
        )
        self.fault("committed")
        self.finish(journal)

    def finish(self, journal: dict) -> None:
        self.control.maintenance_off(journal["id"])
        self.cleanup_update(journal)
        snapshot = (journal.get("snapshot") or {}).get("name")
        self.snapshots.prune(
            self.settings.snapshot_keep, {snapshot} if snapshot else set()
        )
        self.heartbeat.set(journal["phase"], journal["id"], False)
        detail = journal.get("detail") or ""
        if journal["phase"] == "committed" and is_newer(
            journal["target"], self.settings.version
        ):
            detail += (
                f" The updater itself is still v{self.settings.version}; to update "
                f"it, run in your CipherMoth folder: {RECREATE_UPDATER}"
            )
        self.publish(
            RESULT_STATES[journal["phase"]],
            detail.strip(),
            f"v{journal['target']}",
            phase=journal["phase"],
            id=journal["id"],
            previous=journal["previous"].get("version"),
            snapshot=snapshot,
            action="recreate-updater" if "updater itself" in detail else None,
        )

    def cleanup_update(self, journal: dict) -> None:
        directory = self.update_dir(journal)
        for name in ("env.before", "env.target"):
            with suppress(FileNotFoundError):
                (directory / name).unlink()
        with suppress(OSError):
            directory.rmdir()

    def abort(self, journal: dict, reason: str) -> None:
        log(f"update failed before any change: {reason}")
        previous = journal["previous"].get("version", "?")
        if not journal.get("quiesced"):
            self.transition(journal, "failed", detail=f"{reason}. Nothing was changed.")
            self.finish(journal)
            return
        try:
            verify_db, _, _ = self.database_names(journal)
            with suppress(StepError):
                self.pg.drop(verify_db)
            snapshot = journal.get("snapshot") or {}
            if snapshot.get("name") and snapshot.get("state") != "verified":
                self.snapshots.discard(snapshot["name"])
            self.restore_env(journal)
            try:
                self.docker.compose("start", "backend", timeout=300)
            except StepError:
                self.docker.compose("up", "-d", *SERVICES, timeout=900)
            self.wait_healthy(previous, journal["previous"]["images"])
        except (StepError, OSError) as error:
            self.intervention(
                journal,
                f"{reason}; restarting v{previous} afterwards failed too ({error})",
            )
            return
        self.transition(
            journal,
            "failed",
            detail=f"{reason}. Nothing was changed; v{previous} is running again.",
        )
        self.finish(journal)

    def restore_env(self, journal: dict) -> None:
        before = (self.update_dir(journal) / "env.before").read_bytes()
        if hashlib.sha256(before).hexdigest() != journal["previous"]["env_sha256"]:
            raise StepError("the saved copy of .env is damaged")
        if self.read_env() != before:
            self.write_env(before, journal)

    def rollback(self, journal: dict, reason: str) -> None:
        state = journal["rollback"]
        if journal["phase"] == ROLLING_BACK:
            state["resumes"] = state.get("resumes", 0) + 1
            self.journal.save(journal)
            if state["resumes"] > self.settings.rollback_resumes:
                self.intervention(
                    journal,
                    f"the updater stopped {state['resumes'] - 1} times while rolling "
                    "back",
                )
                return
        else:
            state["reason"] = reason
            self.transition(journal, ROLLING_BACK)
        while True:
            try:
                self.rollback_once(journal)
                return
            except (StepError, OSError) as error:
                log(f"rollback attempt failed: {error}")
                state["attempts"] += 1
                state["last_error"] = str(error)
                self.journal.save(journal)
                if state["attempts"] >= self.settings.rollback_attempts:
                    self.intervention(
                        journal,
                        f"rolling back failed {state['attempts']} times (last error: "
                        f"{error})",
                    )
                    return
                self.sleep(min(30.0, self.settings.retry_interval * state["attempts"]))

    def rollback_once(self, journal: dict) -> None:
        previous = journal["previous"]
        self.maintenance_on(journal, snapshot_verified=True)
        self.docker.compose("stop", *SERVICES, timeout=180)
        self.require_stopped(*SERVICES)
        self.fault("rollback_stopped")
        if journal.get("applied"):
            self.restore_snapshot(journal)
        self.restore_env(journal)
        self.fault("rollback_env")
        for service in SERVICES:
            self.restore_image(previous["images"][service])
        self.docker.compose("up", "-d", *SERVICES, timeout=900)
        self.fault("rollback_started")
        for service in SERVICES:
            container = self.docker.container(service)
            if (
                container is None
                or container.get("Image") != (previous["images"][service]["id"])
            ):
                raise StepError(
                    f"the {service} container does not run v{previous['version']}"
                )
        self.wait_healthy(previous["version"], previous["images"])
        _, _, retired = self.database_names(journal)
        self.pg.drop(retired)
        snapshot = journal.get("snapshot") or {}
        reason = journal["rollback"].get("reason", "the update failed")
        restored = (
            f" The database was restored from the snapshot taken at "
            f"{snapshot.get('created_at')}; no change made before the update was lost."
            if journal.get("applied")
            else ""
        )
        self.transition(
            journal,
            "rolled_back",
            detail=f"v{journal['target']} failed ({reason}). Rolled back to "
            f"v{previous['version']}.{restored}",
        )
        self.finish(journal)

    def restore_image(self, image: dict) -> None:
        current = self.docker.image(image["ref"])
        if current is not None and current.get("Id") == image["id"]:
            return
        if self.docker.image(image["id"]) is None:
            self.docker.pull(image["digest"])
            pulled = self.docker.image(image["digest"])
            if pulled is None or pulled.get("Id") != image["id"]:
                raise StepError("the previous image could not be recovered")
        self.docker.tag(image["id"], image["ref"])

    def restore_snapshot(self, journal: dict) -> None:
        if journal["rollback"].get("swapped"):
            return
        database = self.settings.pg_database
        _, replacement, retired = self.database_names(journal)
        if self.pg.exists(retired):
            journal["rollback"]["swapped"] = True
            self.journal.save(journal)
            return
        name = (journal.get("snapshot") or {}).get("name")
        manifest = self.snapshots.verified(name) if isinstance(name, str) else None
        if manifest is None or not isinstance(name, str):
            raise StepError("the pre-update snapshot is missing or damaged")
        self.pg.terminate(database)
        if self.pg.other_connections(database):
            raise StepError("something is still connected to the database")
        self.pg.drop(replacement)
        self.pg.create(replacement)
        self.pg.restore(self.snapshots.dump_path(name), replacement)
        if self.pg.fingerprint(replacement) != manifest["fingerprint"]:
            raise StepError("the restored snapshot does not match its manifest")
        self.fault("restore_created")
        self.pg.swap(database, replacement, retired)
        journal["rollback"]["swapped"] = True
        self.journal.save(journal)
        log(f"database restored from snapshot {name}")
        self.fault("restore_swapped")

    def intervention(self, journal: dict, reason: str) -> None:
        if journal["phase"] != INTERVENTION:
            journal["recover_from"] = journal["phase"]
        snapshot = (journal.get("snapshot") or {}).get("name")
        kept = f" The pre-update snapshot {snapshot} is kept." if snapshot else ""
        self.transition(
            journal,
            INTERVENTION,
            detail=(
                f"The update to v{journal['target']} needs manual attention: {reason}."
                f"{kept} One-click updates are paused and the API stays in "
                "maintenance mode; follow 'Manual recovery' in docs/UPDATING.md."
            ),
        )
        self.heartbeat.set(INTERVENTION, journal["id"], False)
        log(f"INTERVENTION REQUIRED: {reason}")

    def reconcile(self) -> None:
        try:
            journal = self.journal.load()
        except JournalUnreadable as error:
            log(f"INTERVENTION REQUIRED: {error}")
            self.publish(
                INTERVENTION,
                f"The updater cannot read its journal ({error}). One-click updates "
                "are paused; follow 'Manual recovery' in docs/UPDATING.md.",
                None,
            )
            self.heartbeat.set(INTERVENTION, None, False)
            return
        if journal is None:
            self.drop_stray_databases(None)
            self.reconcile_legacy()
            return
        phase = journal["phase"]
        if phase == INTERVENTION:
            self.heartbeat.set(INTERVENTION, journal["id"], False)
            log("a previous update needs manual attention; not taking requests")
            return
        if phase in TERMINAL:
            self.drop_stray_databases(journal)
            unfinished = self.control.maintenance_owner() == journal["id"]
            if phase != "resolved" and (
                unfinished or self.update_dir(journal).exists()
            ):
                self.finish(journal)
            return
        log(f"recovering an interrupted update (phase {phase})")
        self.wait_for_dependencies()
        self.drop_stray_databases(journal)
        if phase in ("preparing", "verifying", "snapshotting"):
            self.abort(
                journal, "The updater was interrupted before applying the update"
            )
        elif phase in ("applying", "validating"):
            self.rollback(journal, "the updater was interrupted while applying it")
        elif phase == ROLLING_BACK:
            self.rollback(journal, journal["rollback"].get("reason", "interrupted"))
        else:
            self.intervention(journal, f"the journal is in an unknown phase {phase!r}")

    def wait_for_dependencies(self) -> None:
        deadline = time.monotonic() + self.settings.dependency_timeout
        while True:
            try:
                self.runner.run(
                    ["docker", "version", "--format", "{{.Server.Version}}"],
                    timeout=30,
                    what="docker version",
                )
                self.pg.query("SELECT 1")
                return
            except StepError as error:
                if time.monotonic() > deadline:
                    log(
                        f"Docker or the database is still unavailable ({error}); "
                        "exiting so the restart policy retries later"
                    )
                    raise SystemExit(1) from error
                log(f"waiting for Docker and the database before recovering: {error}")
                self.sleep(self.settings.retry_interval)

    def drop_stray_databases(self, journal: dict | None) -> None:
        active = None
        if journal is not None and journal["phase"] not in TERMINAL:
            active = journal["id"]
        pattern = re.compile(
            rf"{re.escape(self.settings.pg_database)}_(verify|restore)_([0-9a-f]{{32}})"
        )
        try:
            names = self.pg.list_databases()
        except StepError:
            return
        for name in names:
            match = pattern.fullmatch(name)
            if match and match.group(2) != active:
                log(f"dropping leftover database {name}")
                with suppress(StepError):
                    self.pg.drop(name)

    def reconcile_legacy(self) -> None:
        result = read_json(self.control.result) or {}
        if result.get("protocol") or result.get("state") not in (
            "verifying",
            "applying",
        ):
            return
        running = self.running_version()
        if running is None:
            log("an interrupted update by the previous updater left the backend down")
            self.publish(
                "failed",
                "An update started by the previous updater was interrupted and "
                "the backend is not answering; run `docker compose -f "
                "docker-compose.prod.yml up -d` and check the logs.",
                result.get("target"),
            )
            return
        env = self.read_env()
        configured = env_version(env)
        if parse_version(configured) is not None and parse_version(
            configured
        ) != parse_version(running):
            info = os.stat(self.settings.env_file)
            write_atomic(
                self.settings.env_file,
                with_version(env, plain_version(running)),
                mode=stat.S_IMODE(info.st_mode),
                owner=(info.st_uid, info.st_gid),
            )
            log(f".env named {configured}; set it back to the running {running}")
        self.publish(
            "failed",
            f"An update started by the previous updater was interrupted. "
            f"v{plain_version(running)} is running.",
            result.get("target"),
        )

    def resolve(self) -> int:
        try:
            journal = self.journal.load()
        except JournalUnreadable as error:
            log(f"the journal is unreadable ({error}); moving it aside")
            os.replace(
                self.journal.path, self.journal.path.with_suffix(f".{int(time.time())}")
            )
            with suppress(FileNotFoundError):
                os.unlink(self.control.maintenance)
            self.publish("failed", "The update state was reset by hand.", None)
            self.heartbeat.set(None, None, False)
            return 0
        if journal is None or journal["phase"] != INTERVENTION:
            log("nothing to resolve")
            return 1
        self.control.maintenance_off(journal["id"])
        self.transition(journal, "resolved", detail="Resolved by hand after an update.")
        self.cleanup_update(journal)
        return 0

    def serve(self) -> None:
        self.setup()
        with self.locked():
            write_atomic(self.control.ready, b"")
            self.heartbeat.start()
            try:
                self.recover()
                log(f"ready (protocol {PROTOCOL}, version {self.settings.version})")
                while True:
                    self.operator_requests()
                    if self.control.has_request():
                        self.handle_request()
                    self.sleep(self.settings.poll_interval)
            finally:
                self.heartbeat.stop()

    def recover(self) -> None:
        try:
            self.reconcile()
        except OSError as error:
            log(f"cannot recover now ({error}); exiting so it is retried later")
            self.sleep(self.settings.retry_interval * 6)
            raise SystemExit(1) from error

    def operator_marker(self, command: str) -> Path:
        return self.state_dir / f"{command}.requested"

    def operator_requests(self) -> None:
        for command in OPERATOR_COMMANDS:
            marker = self.operator_marker(command)
            if marker.exists():
                with suppress(FileNotFoundError):
                    marker.unlink()
                log(f"operator asked to {command}")
                code = self.operate(command)
                write_atomic(
                    marker.with_suffix(".done"), str(code).encode(), mode=0o600
                )

    def operate(self, command: str) -> int:
        if command == "resolve":
            return self.resolve()
        return self.retry()

    def operator(self, command: str) -> int:
        self.setup()
        handle = (self.state_dir / "lock").open("a+")
        try:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                marker = self.operator_marker(command)
                done = marker.with_suffix(".done")
                with suppress(FileNotFoundError):
                    done.unlink()
                write_atomic(marker, timestamp().encode(), mode=0o600)
                log(f"handing '{command}' to the running updater")
                deadline = time.monotonic() + 3600
                while time.monotonic() < deadline:
                    outcome = read_bounded(done, 16)
                    if outcome is not None:
                        done.unlink()
                        print(json.dumps(read_json(self.journal.path), indent=2))
                        return int(outcome or b"1")
                    time.sleep(0.5)
                log("the running updater did not finish within an hour")
                return 1
            return self.operate(command)
        finally:
            handle.close()

    def retry(self) -> int:
        try:
            journal = self.journal.load()
        except JournalUnreadable as error:
            log(f"cannot retry: {error}; use resolve")
            return 1
        if journal is None or journal["phase"] != INTERVENTION:
            log("nothing to retry")
            return 1
        origin = journal.get("recover_from")
        if origin not in (*ACTIVE, ROLLING_BACK):
            log("this update cannot be retried automatically; use resolve")
            return 1
        journal["rollback"].update({"attempts": 0, "resumes": 0})
        self.transition(journal, origin, detail="Retrying the recovery by request")
        self.recover()
        after = self.journal.load()
        return 0 if after is not None and after["phase"] != INTERVENTION else 1

    def once(self) -> None:
        self.setup()
        with self.locked():
            self.heartbeat.beat()
            try:
                self.recover()
                self.operator_requests()
                if self.control.has_request():
                    self.handle_request()
            finally:
                self.heartbeat.beat(running=False)


def _terminate(signum: int, frame: object) -> None:
    raise SystemExit(128 + signum)


def main(argv: list[str]) -> int:
    command = argv[1] if len(argv) > 1 else "run"
    if command == "newer":
        return 0 if is_newer(argv[2], argv[3]) else 1
    signal.signal(signal.SIGTERM, _terminate)
    updater = Updater(Settings.from_env())
    if command == "run":
        updater.serve()
        return 0
    if command == "once":
        updater.once()
        return 0
    if command == "status":
        updater.setup()
        print(json.dumps(updater.journal.load(), indent=2))
        return 0
    if command in OPERATOR_COMMANDS:
        return updater.operator(command)
    if command == "verify-image":
        updater.verify_signature(argv[2])
        return 0
    print(
        "usage: updater.py [run|once|status|retry|resolve|newer A B|verify-image REF]",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
