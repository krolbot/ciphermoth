import hashlib
import json
import os
import subprocess
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UPDATER = ROOT / "docker" / "updater" / "updater.py"
FAKE = Path(__file__).resolve().with_name("fake_updater_world.py")
REPO = "ghcr.io/mr-grj/ciphermoth"
LABEL = "io.ciphermoth.min-updater-protocol"
DB_PASSWORD = "db-secret-Zq7"
PROGRAMS = ("docker", "cosign", "psql", "pg_dump", "pg_restore", "curl")


def image_id(name: str) -> str:
    return "sha256:" + hashlib.sha256(name.encode()).hexdigest()


def initial_database(revision: str) -> dict:
    return {
        "alembic": revision,
        "schema": f"schema-{revision}",
        "sequence": 3,
        "tables": {
            "public.alembic_version": [[revision]],
            "public.master_password": [["$2b$12$hash", "salt", "key-check"]],
            "public.passwords": [
                [1, "github", "gAAAAAciphertext", None],
                [2, "trashed", "gAAAAAold", "2026-10-01"],
            ],
            "public.password_attachments": [[1, 1, "gAAAAAfile", 4096]],
            "public.settings": [[1, 900000, 60000]],
        },
    }


class World:
    def __init__(self, tmp_path: Path, running: str = "1.5.1") -> None:
        self.root = tmp_path
        self.bin = tmp_path / "bin"
        self.control = tmp_path / "control"
        self.backups = tmp_path / "backups"
        self.dir = tmp_path / "world"
        for directory in (self.bin, self.control, self.dir):
            directory.mkdir()
        self.env_file = tmp_path / ".env"
        self.env_file.write_text(
            f"POSTGRES_PASSWORD={DB_PASSWORD}\nCIPHERMOTH_VERSION={running}\n"
            "OTHER=kept\n"
        )
        os.chmod(self.env_file, 0o640)
        for program in PROGRAMS:
            stub = self.bin / program
            stub.write_text(
                f"#!{sys.executable} -S\n"
                "import os, sys\n"
                f"os.environ['FAKE_PROGRAM'] = {program!r}\n"
                f"sys.path.insert(0, {str(FAKE.parent)!r})\n"
                "import fake_updater_world\n"
                "fake_updater_world.main()\n"
            )
            stub.chmod(0o755)
        self.state: dict = {
            "images": {},
            "tags": {},
            "registry": {},
            "containers": {},
            "databases": {"ciphermoth": initial_database("rev1")},
            "live_db": "ciphermoth",
            "original_version": running,
            "compose_repo": REPO,
            "flags": [],
            "unsigned": [],
        }
        self.release(running, local=True)
        for service in ("backend", "frontend"):
            ref = f"{REPO}-{service}:{running}"
            self.state["containers"][service] = {
                "image": self.state["tags"][ref],
                "ref": ref,
                "running": True,
                "restarts": 0,
            }
        self.save()
        self.process: subprocess.CompletedProcess[str] | None = None

    def save(self) -> None:
        (self.dir / "world.json").write_text(json.dumps(self.state, indent=1))

    def load(self) -> dict:
        self.state = json.loads((self.dir / "world.json").read_text())
        return self.state

    def release(
        self,
        version: str,
        *,
        local: bool = False,
        aware: bool = True,
        migrate_to: str | None = None,
        migration_fails: bool = False,
        min_protocol: str | None = None,
        signed: bool = True,
        head: str | None = None,
    ) -> None:
        for service in ("backend", "frontend"):
            key = image_id(f"{service}-{version}-{migrate_to}-{migration_fails}")
            digest = f"{REPO}-{service}@{image_id(f'digest-{key}')}"
            labels = {LABEL: min_protocol or "2"} if aware else {}
            image: dict = {
                "version": version,
                "digests": [digest],
                "labels": labels,
                "aware": aware,
            }
            if service == "backend":
                image["head"] = head or migrate_to or "rev1"
                if migrate_to:
                    image["migrate"] = {"to": migrate_to, "fails": migration_fails}
            self.state["images"][key] = image
            ref = f"{REPO}-{service}:{version}"
            self.state["registry"][ref] = key
            if local:
                self.state["tags"][ref] = key
            if not signed:
                self.state["unsigned"].append(digest)
        self.save()

    def flag(self, *names: str) -> None:
        self.load()
        self.state["flags"].extend(names)
        self.save()

    def unflag(self, *names: str) -> None:
        self.load()
        self.state["flags"] = [f for f in self.state["flags"] if f not in names]
        self.save()

    def request(self, target: str, **fields: object) -> dict:
        payload: dict = {
            "target": target,
            "id": uuid.uuid4().hex,
            "requested_at": datetime.now(UTC).isoformat(),
        }
        payload.update(fields)
        payload = {k: v for k, v in payload.items() if v is not None}
        (self.control / "request.json").write_text(json.dumps(payload))
        return payload

    def environment(self, **extra: str) -> dict[str, str]:
        env = {
            **os.environ,
            "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}",
            "FAKE_WORLD": str(self.dir),
            "UPDATE_CONTROL_DIR": str(self.control),
            "ENV_FILE": str(self.env_file),
            "COMPOSE_FILE": str(self.root / "docker-compose.prod.yml"),
            "BACKUP_DIR": str(self.backups),
            "IMAGE_REPO": REPO,
            "HEALTH_RETRIES": "2",
            "HEALTH_INTERVAL": "0",
            "HEALTH_STABLE": "1",
            "POLL_INTERVAL": "0.05",
            "HEARTBEAT_INTERVAL": "0.2",
            "RETRY_INTERVAL": "0",
            "DEPENDENCY_TIMEOUT": "2",
            "ROLLBACK_ATTEMPTS": "2",
            "CIPHERMOTH_UPDATER_VERSION": "1.5.1",
            "PGPASS_PATH": str(self.root / "pgpass"),
            "POSTGRES_HOST": "db",
            "POSTGRES_PORT": "5432",
            "POSTGRES_USER": "ciphermoth",
            "POSTGRES_DB": "ciphermoth",
            "POSTGRES_PASSWORD": DB_PASSWORD,
            "CIPHERMOTH_UPDATER_FAULT": "",
        }
        env.update(extra)
        return env

    def run(
        self, command: str = "once", *, timeout: float = 120, **extra: str
    ) -> subprocess.CompletedProcess[str]:
        args = [sys.executable, str(UPDATER), *command.split()]
        self.process = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=self.environment(**extra),
        )
        self.load()
        return self.process

    def serve_for(
        self, seconds: float, **extra: str
    ) -> subprocess.CompletedProcess[str]:
        process = subprocess.Popen(
            [sys.executable, str(UPDATER), "run"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=self.environment(**extra),
        )
        try:
            stdout, stderr = process.communicate(timeout=seconds)
        except subprocess.TimeoutExpired:
            process.terminate()
            stdout, stderr = process.communicate(timeout=30)
        self.process = subprocess.CompletedProcess(
            process.args, process.returncode, stdout, stderr
        )
        self.load()
        return self.process

    @property
    def log(self) -> str:
        return self.process.stderr if self.process else ""

    @property
    def result(self) -> dict:
        return json.loads((self.control / "result.json").read_text())

    @property
    def journal(self) -> dict:
        return json.loads((self.backups / "state" / "journal.json").read_text())

    @property
    def calls(self) -> list[str]:
        path = self.dir / "calls.log"
        return path.read_text().splitlines() if path.exists() else []

    def index(self, prefix: str) -> int:
        return next(i for i, line in enumerate(self.calls) if line.startswith(prefix))

    def indexes(self, needle: str) -> list[int]:
        return [i for i, line in enumerate(self.calls) if needle in line]

    @property
    def env_version(self) -> str:
        version = ""
        for line in self.env_file.read_text().splitlines():
            if line.startswith("CIPHERMOTH_VERSION="):
                version = line.split("=", 1)[1]
        return version

    def running(self, service: str = "backend") -> str | None:
        container = self.state["containers"][service]
        if not container["running"]:
            return None
        return self.state["images"][container["image"]]["version"]

    @property
    def live_db(self) -> dict:
        return self.state["databases"][self.state["live_db"]]

    @property
    def database_names(self) -> list[str]:
        return sorted(self.state["databases"])

    @property
    def maintenance(self) -> dict | None:
        path = self.control / "maintenance.json"
        return json.loads(path.read_text()) if path.exists() else None

    @property
    def snapshots(self) -> list[str]:
        directory = self.backups / "snapshots"
        return sorted(p.name for p in directory.iterdir()) if directory.exists() else []

    def write_data(self, row: list) -> None:
        self.load()
        self.live_db["tables"]["public.passwords"].append(row)
        self.save()

    def secrets_leaked(self) -> list[str]:
        leaks = []
        for path in [*self.control.rglob("*"), *self.backups.rglob("*.json")]:
            if path.is_file() and DB_PASSWORD in path.read_text(errors="replace"):
                leaks.append(str(path))
        if DB_PASSWORD in self.log:
            leaks.append("updater log")
        if any(DB_PASSWORD in line for line in self.calls):
            leaks.append("command line")
        return leaks


def stale_time(minutes: int) -> str:
    return (datetime.now(UTC) - timedelta(minutes=minutes)).isoformat()
