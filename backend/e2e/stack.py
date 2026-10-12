import asyncio
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from tests.integrity import VaultContents, raw_vault, read_vault

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "testdata" / "golden" / "v1.4.6"
REGISTRY = os.environ.get("E2E_REGISTRY", "localhost:5555")
REGISTRY_CONTAINER = "cm-e2e-registry"
PUBLISHED = os.environ.get("E2E_PUBLISHED", "1.5.0")
CANDIDATE = os.environ.get("E2E_CANDIDATE", "1.5.1")
PROJECT_PREFIX = "cm-e2e-"
WORK = Path(
    os.environ.get("E2E_WORKDIR") or tempfile.mkdtemp(prefix="ciphermoth-e2e-")
).resolve()
FIXTURES = Path(__file__).resolve().parent / "fixtures"
COSIGN_STUB = (
    "#!/bin/sh\n"
    'echo "COSIGN STUBBED FOR E2E (locally built images are unsigned): $*" >&2\n'
    "exit 0\n"
)
TERMINAL = {"success", "failed", "rolled_back", "intervention"}


def clean_environment() -> dict[str, str]:
    return {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("POSTGRES_", "CIPHERMOTH_", "UPDATE_CONTROL", "E2E_"))
    }


def sh(
    *args: str,
    cwd: Path | None = None,
    check: bool = True,
    timeout: float = 1800,
    stdin: bytes | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        list(args),
        cwd=cwd,
        input=stdin.decode() if stdin is not None else None,
        capture_output=True,
        text=True,
        timeout=timeout,
        env={**clean_environment(), **(env or {})},
    )
    if check and proc.returncode != 0:
        raise RuntimeError(
            f"{' '.join(args[:6])} failed ({proc.returncode}):\n"
            f"{proc.stdout[-3000:]}\n{proc.stderr[-3000:]}"
        )
    return proc


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def ensure_registry() -> None:
    running = sh(
        "docker",
        "inspect",
        "-f",
        "{{.State.Running}}",
        REGISTRY_CONTAINER,
        check=False,
    )
    if running.stdout.strip() == "true":
        return
    sh("docker", "rm", "-f", REGISTRY_CONTAINER, check=False)
    port = REGISTRY.rsplit(":", 1)[1]
    sh(
        "docker",
        "run",
        "-d",
        "--name",
        REGISTRY_CONTAINER,
        "-p",
        f"127.0.0.1:{port}:5000",
        "registry:2",
    )
    time.sleep(2)


def publish(source: str, name: str, version: str) -> str:
    ref = f"{REGISTRY}/{name}:{version}"
    sh("docker", "tag", source, ref)
    sh("docker", "push", "-q", ref)
    sh("docker", "rmi", ref)
    sh("docker", "pull", "-q", ref)
    return ref


def build(context: Path, dockerfile: Path, tag: str, *args: str) -> str:
    sh(
        "docker",
        "build",
        "-q",
        "--provenance=false",
        "-f",
        str(dockerfile),
        "-t",
        tag,
        *args,
        str(context),
    )
    return tag


def derived(tag: str, dockerfile: str, files: dict[str, str] | None = None) -> str:
    context = WORK / "derived" / tag.replace("/", "_").replace(":", "_")
    shutil.rmtree(context, ignore_errors=True)
    context.mkdir(parents=True)
    (context / "Dockerfile").write_text(dockerfile)
    for name, content in (files or {}).items():
        (context / name).write_text(content)
    return build(context, context / "Dockerfile", tag)


@dataclass
class Release:
    version: str
    migration: str | None = None
    frontend_error: bool = False


SYNTHETIC = [
    Release("1.5.2"),
    Release("1.5.3", migration="e2e_good_migration.py"),
    Release("1.5.4", migration="e2e_failing_migration.py"),
    Release("1.5.5", migration="e2e_good_migration.py", frontend_error=True),
]


def candidate_context() -> Path:
    context = WORK / "candidate"
    shutil.rmtree(context, ignore_errors=True)
    context.mkdir(parents=True)
    sh(
        "rsync",
        "-a",
        "--exclude=.git",
        "--exclude=node_modules",
        "--exclude=.venv",
        "--exclude=dist",
        "--exclude=__pycache__",
        "--exclude=private",
        "--exclude=docs/architecture",
        "--exclude=CLAUDE.md",
        f"{ROOT}/",
        f"{context}/",
    )
    pyproject = context / "backend" / "pyproject.toml"
    pyproject.write_text(
        re.sub(
            r'^version = ".*"$',
            f'version = "{CANDIDATE}"',
            pyproject.read_text(),
            count=1,
            flags=re.M,
        )
    )
    package = context / "frontend" / "package.json"
    data = json.loads(package.read_text())
    data["version"] = CANDIDATE
    package.write_text(json.dumps(data, indent=2) + "\n")
    return context


def build_images() -> dict[str, str]:
    ensure_registry()
    refs: dict[str, str] = {}
    for service in ("backend", "frontend"):
        source = f"ghcr.io/mr-grj/ciphermoth-{service}:{PUBLISHED}"
        sh("docker", "pull", "-q", source)
        wrapped = derived(f"cm-e2e/{service}:published", f"FROM {source}\n")
        refs[f"{service}:{PUBLISHED}"] = publish(
            wrapped, f"ciphermoth-{service}", PUBLISHED
        )
    old_updater = f"ghcr.io/mr-grj/ciphermoth-updater:{PUBLISHED}"
    sh("docker", "pull", "-q", old_updater)
    refs[f"updater:{PUBLISHED}"] = publish(
        derived(
            "cm-e2e/updater:published-stubbed",
            f"FROM {old_updater}\nCOPY cosign /usr/bin/cosign\n"
            "RUN chmod 755 /usr/bin/cosign\n"
            'LABEL io.ciphermoth.e2e="cosign-stubbed"\n',
            {"cosign": COSIGN_STUB},
        ),
        "ciphermoth-updater",
        PUBLISHED,
    )

    context = candidate_context()
    docker = context / "docker"
    backend = build(context, docker / "backend" / "Dockerfile", "cm-e2e/backend:cand")
    frontend = build(
        context,
        docker / "frontend" / "Dockerfile",
        "cm-e2e/frontend:cand",
        "--build-arg",
        "VITE_API_URL=__CIPHERMOTH_API_URL__",
    )
    refs["updater:real"] = build(
        context, docker / "updater" / "Dockerfile", "cm-e2e/updater:real"
    )
    refs[f"backend:{CANDIDATE}"] = publish(backend, "ciphermoth-backend", CANDIDATE)
    refs[f"frontend:{CANDIDATE}"] = publish(frontend, "ciphermoth-frontend", CANDIDATE)
    stubbed = derived(
        "cm-e2e/updater:cand-stubbed",
        "FROM cm-e2e/updater:real\nCOPY cosign /usr/bin/cosign\n"
        "RUN chmod 755 /usr/bin/cosign\n"
        'LABEL io.ciphermoth.e2e="cosign-stubbed"\n',
        {"cosign": COSIGN_STUB},
    )
    for release in [Release(CANDIDATE), *SYNTHETIC]:
        refs[f"updater:{release.version}"] = publish(
            stubbed, "ciphermoth-updater", release.version
        )

    for release in SYNTHETIC:
        files = {}
        steps = [
            "FROM cm-e2e/backend:cand",
            "USER root",
            f'RUN sed -i \'s/^version = ".*"$/version = "{release.version}"/\' '
            "/app/src/pyproject.toml",
        ]
        if release.migration:
            files["migration.py"] = (FIXTURES / release.migration).read_text()
            steps.append(
                "COPY migration.py /app/src/migrations/ciphermoth/versions/"
                f"{release.migration}"
            )
        steps.append("USER ciphermoth")
        image = derived(
            f"cm-e2e/backend:{release.version}", "\n".join(steps) + "\n", files
        )
        refs[f"backend:{release.version}"] = publish(
            image, "ciphermoth-backend", release.version
        )
        steps = [
            "FROM cm-e2e/frontend:cand",
            "USER root",
            f'RUN printf \'{{"version":"{release.version}"}}\\n\' > '
            "/app/dist/version.json",
        ]
        if release.frontend_error:
            files = {"entrypoint.sh": (FIXTURES / "frontend_error.sh").read_text()}
            steps += [
                "COPY entrypoint.sh /app/entrypoint.sh",
                "RUN chmod 755 /app/entrypoint.sh",
            ]
        else:
            files = {}
        steps.append("USER ciphermoth")
        image = derived(
            f"cm-e2e/frontend:{release.version}", "\n".join(steps) + "\n", files
        )
        refs[f"frontend:{release.version}"] = publish(
            image, "ciphermoth-frontend", release.version
        )
    return refs


def compose_file(
    project: str,
    source: str,
    updater_image: str | None,
    registry: str | None = REGISTRY,
) -> str:
    text_value = sh("git", "show", f"{source}:docker-compose.prod.yml", cwd=ROOT).stdout
    repo = registry or "ghcr.io/mr-grj"
    replacements = [
        ("name: ciphermoth\n", f"name: {project}\n"),
        ("ghcr.io/mr-grj/ciphermoth-", f"{repo}/ciphermoth-"),
        (
            "IMAGE_REPO: ghcr.io/mr-grj/ciphermoth\n",
            f"IMAGE_REPO: {repo}/ciphermoth\n",
        ),
        (
            "    image: postgres:16-alpine\n",
            "    image: postgres:16-alpine\n"
            '    ports:\n      - "127.0.0.1:${E2E_DB_PORT}:5432"\n',
        ),
        (
            f"      IMAGE_REPO: {repo}/ciphermoth\n",
            f"      IMAGE_REPO: {repo}/ciphermoth\n"
            "      HEALTH_RETRIES: ${E2E_HEALTH_RETRIES:-30}\n"
            "      HEALTH_INTERVAL: ${E2E_HEALTH_INTERVAL:-2}\n"
            "      POLL_INTERVAL: 1\n"
            "      CIPHERMOTH_UPDATER_FAULT: ${E2E_FAULT:-}\n",
        ),
    ]
    for old, new in replacements:
        if old not in text_value:
            raise AssertionError(f"compose file of {source} lacks {old!r}")
        text_value = text_value.replace(old, new)
    head, updater = text_value.split("  updater:\n", 1)
    host = "      POSTGRES_HOST: db\n"
    if host not in updater:
        raise AssertionError("updater POSTGRES_HOST not found")
    updater = updater.replace(host, "      POSTGRES_HOST: ${E2E_UPDATER_DB_HOST:-db}\n")
    if updater_image:
        image = f"{repo}/ciphermoth-updater:${{CIPHERMOTH_VERSION:-latest}}"
        if f"    image: {image}\n" not in updater:
            raise AssertionError("updater image line not found")
        updater = updater.replace(image, updater_image, 1)
    return head + "  updater:\n" + updater


class Stack:
    def __init__(
        self,
        name: str,
        version: str = CANDIDATE,
        *,
        compose_source: str = f"v{PUBLISHED}",
        fault: str = "",
        updater_image: str | None = None,
        extra_env: dict[str, str] | None = None,
        updater_restart: str | None = None,
        registry: str | None = REGISTRY,
    ) -> None:
        self.project = f"{PROJECT_PREFIX}{name}"
        if self.project == "ciphermoth" or not self.project.startswith(PROJECT_PREFIX):
            raise AssertionError("refusing to touch a real CipherMoth project")
        self.dir = WORK / "stacks" / name
        shutil.rmtree(self.dir, ignore_errors=True)
        self.dir.mkdir(parents=True)
        self.backend_port = free_port()
        self.frontend_port = free_port()
        self.db_port = free_port()
        self.db_password = secrets.token_urlsafe(24)
        compose = compose_file(self.project, compose_source, updater_image, registry)
        if updater_restart:
            old = '    restart: unless-stopped\n    profiles: ["autoupdate"]\n'
            if old not in compose:
                raise AssertionError("updater restart policy not found")
            compose = compose.replace(
                old, f'    restart: "{updater_restart}"\n    profiles: ["autoupdate"]\n'
            )
        (self.dir / "docker-compose.prod.yml").write_text(compose)
        env = {
            "POSTGRES_PASSWORD": self.db_password,
            "CIPHERMOTH_VERSION": version,
            "CIPHERMOTH_BACKEND_PORT": str(self.backend_port),
            "CIPHERMOTH_FRONTEND_PORT": str(self.frontend_port),
            "CIPHERMOTH_API_URL": f"http://localhost:{self.backend_port}/api",
            "CIPHERMOTH_FRONTEND_ORIGIN": f"http://localhost:{self.frontend_port}",
            "E2E_DB_PORT": str(self.db_port),
            "E2E_FAULT": fault,
            **(extra_env or {}),
        }
        lines = ["# e2e stack, safe to delete", *(f"{k}={v}" for k, v in env.items())]
        (self.dir / ".env").write_text("\n".join(lines) + "\n")
        self.api = httpx.Client(
            base_url=f"http://127.0.0.1:{self.backend_port}/api", timeout=30
        )

    def compose(self, *args: str, check: bool = True, timeout: float = 900):
        return sh(
            "docker",
            "compose",
            "-f",
            str(self.dir / "docker-compose.prod.yml"),
            "--profile",
            "autoupdate",
            *args,
            cwd=self.dir,
            check=check,
            timeout=timeout,
        )

    def start(self, golden: bool = True) -> None:
        self.compose("up", "-d", "--wait", "db")
        if golden:
            dump = (GOLDEN / "dump.sql").read_bytes()
            sh(
                "docker",
                "compose",
                "-f",
                str(self.dir / "docker-compose.prod.yml"),
                "exec",
                "-T",
                "db",
                "psql",
                "-q",
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                "ciphermoth",
                "-d",
                "ciphermoth",
                "-f",
                "-",
                cwd=self.dir,
                stdin=dump,
            )
        self.compose("up", "-d")
        self.wait_for(lambda: self.meta() is not None, 180, "backend")
        self.wait_for(lambda: self.updater_heartbeat(), 120, "updater")

    def down(self) -> None:
        self.api.close()
        self.compose("down", "-v", "--remove-orphans", check=False)
        shutil.rmtree(self.dir, ignore_errors=True)

    def wait_for(self, condition, timeout: float, what: str):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                value = condition()
            except (httpx.HTTPError, ValueError):
                value = None
            if value:
                return value
            time.sleep(1)
        raise AssertionError(f"timed out waiting for {what}\n{self.logs()}")

    def logs(self, *services: str) -> str:
        proc = self.compose(
            "logs", "--no-color", "--tail", "120", *services, check=False
        )
        return proc.stdout[-12000:]

    def meta(self) -> str | None:
        resp = self.api.get("/meta", timeout=5)
        return resp.json()["version"] if resp.status_code == 200 else None

    def updater_heartbeat(self) -> bool:
        resp = self.api.get("/updates/apply/status", timeout=5)
        return resp.status_code == 200 and resp.json().get("updater_present")

    def status(self) -> dict | None:
        try:
            resp = self.api.get("/updates/apply/status", timeout=5)
        except httpx.HTTPError:
            return None
        return resp.json() if resp.status_code == 200 else None

    def frontend_version(self) -> str | None:
        try:
            resp = httpx.get(
                f"http://127.0.0.1:{self.frontend_port}/version.json", timeout=5
            )
            return resp.json().get("version")
        except (httpx.HTTPError, ValueError):
            return None

    def frontend_page(self) -> str:
        return httpx.get(f"http://127.0.0.1:{self.frontend_port}/", timeout=5).text

    def unlock(self, master_password: str) -> str:
        resp = self.api.post(
            "/master_password/unlock", json={"master_password": master_password}
        )
        assert resp.status_code == 200, resp.text
        return resp.json()["session_token"]

    def headers(self, token: str) -> dict[str, str]:
        return {"x-ciphermoth-session": token}

    def add_entry(self, token: str, name: str) -> httpx.Response:
        return self.api.post(
            "/passwords/create",
            headers=self.headers(token),
            json={"password_name": name, "password_value": f"{name}-Value-1!"},
        )

    def entry_names(self, token: str) -> list[str]:
        resp = self.api.get("/passwords", headers=self.headers(token))
        assert resp.status_code == 200, resp.text
        return sorted(item["password_name"] for item in resp.json())

    def apply(self, token: str, target: str) -> httpx.Response:
        return self.api.post(
            "/updates/apply", headers=self.headers(token), json={"target": target}
        )

    def wait_result(self, request_id: str | None = None, timeout: float = 900) -> dict:
        def finished() -> dict | None:
            status = self.status()
            if not status or status.get("state") not in TERMINAL:
                return None
            if request_id and status.get("id") not in (None, request_id):
                return None
            return status

        return self.wait_for(finished, timeout, "the update result")

    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://ciphermoth:{self.db_password}@127.0.0.1:"
            f"{self.db_port}/ciphermoth"
        )

    def vault(self, key: str, master_password: str) -> tuple[dict, VaultContents]:
        async def scan() -> tuple[dict, VaultContents]:
            engine = create_async_engine(self.database_url())
            try:
                async with engine.connect() as conn:
                    raw = await raw_vault(conn)
                    contents = await read_vault(
                        conn, key, master_password=master_password
                    )
                    return raw, contents
            finally:
                await engine.dispose()

        return asyncio.run(scan())

    def query(self, sql: str) -> list[tuple]:
        async def run() -> list[tuple]:
            engine = create_async_engine(self.database_url())
            try:
                async with engine.connect() as conn:
                    return [tuple(row) for row in await conn.execute(text(sql))]
            finally:
                await engine.dispose()

        return asyncio.run(run())

    def tables(self) -> set[str]:
        return {
            row[0]
            for row in self.query(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
            )
        }

    def revision(self) -> str:
        return self.query("SELECT version_num FROM alembic_version")[0][0]

    def settings_rows(self) -> list[tuple]:
        return self.query("SELECT * FROM settings ORDER BY id")

    def backups(self) -> list[str]:
        proc = sh(
            "docker",
            "run",
            "--rm",
            "-v",
            f"{self.project}_update_backups:/b",
            "alpine:3.21",
            "find",
            "/b",
            "-type",
            "f",
        )
        return sorted(proc.stdout.split())

    def env_version(self) -> str:
        version = ""
        for line in (self.dir / ".env").read_text().splitlines():
            if line.startswith("CIPHERMOTH_VERSION="):
                version = line.split("=", 1)[1]
        return version

    def container(self, service: str) -> dict:
        ids = self.compose("ps", "-a", "-q", service).stdout.split()
        return json.loads(sh("docker", "inspect", ids[0]).stdout)[0]


def golden() -> dict:
    return json.loads((GOLDEN / "expected.json").read_text())
