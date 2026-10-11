"""
Build the golden vault fixtures in testdata/golden from real releases.

For each release, the published backend image (or, for v0.3.0, an image built
from the tag) runs against a throwaway PostgreSQL in its own Docker network.
A synthetic vault is seeded through that release's own API, including a master
password rotation halfway through. Everything is then read back through the
same API as the expected plaintext, a backup is exported, and the database is
dumped with pg_dump. Nothing touches any other container, volume or port.

Run from backend/: uv run python -m tests.tools.generate_golden v1.4.5 [...]
"""

import argparse
import hashlib
import json
import random
import socket
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

import httpx

REPO = Path(__file__).resolve().parents[3]
OUT = REPO / "testdata" / "golden"

FIRST_PASSWORD = "Golden Moth Ünïcode 🦋 2026!"
FINAL_PASSWORD = "Rotated Мотылёк パス 2027?"
DB_USER = "golden"
DB_PASSWORD = "golden-throwaway"
DB_NAME = "ciphermoth"

MODERN = {"history", "update_check", "trash", "attachments", "notes", "meta"}
RELEASES: dict[str, dict] = {
    "v0.3.0": {
        "build_from_tag": True,
        "header": "x-dino-key-derivation",
        "rate_env": "DINOPASS_RATE_LIMIT",
        "features": {"history"},
    },
    "v1.0.0": {"features": {"history"}},
    "v1.1.0": {"features": {"history", "update_check", "meta"}},
    "v1.4.0": {"features": MODERN},
    "v1.4.5": {"features": MODERN},
    "v1.4.6": {"features": MODERN | {"key_check"}},
}


def run(*args: str, **kwargs) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=True, capture_output=True, text=True, **kwargs)


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def image_for(release: str, spec: dict) -> tuple[str, str]:
    if spec.get("build_from_tag"):
        tag = f"ciphermoth-golden-build:{release.lstrip('v')}"
        archive = subprocess.run(
            ["git", "-C", str(REPO), "archive", release],
            check=True,
            capture_output=True,
        ).stdout
        subprocess.run(
            [
                "docker",
                "build",
                "-q",
                "-t",
                tag,
                "-f",
                "docker/backend/Dockerfile",
                "-",
            ],
            input=archive,
            check=True,
            capture_output=True,
        )
        commit = run("git", "-C", str(REPO), "rev-list", "-n1", release).stdout
        return tag, f"built from git tag {release} ({commit.strip()})"
    ref = f"ghcr.io/mr-grj/ciphermoth-backend:{release.lstrip('v')}"
    run("docker", "pull", "-q", ref)
    digest = run(
        "docker", "image", "inspect", "--format", "{{index .RepoDigests 0}}", ref
    ).stdout.strip()
    return ref, digest


def rng_bytes(seed: str, size: int) -> bytes:
    data = random.Random(seed).randbytes(size)
    return b"\xff\xfe\x00\x80" + data[4:]


class Api:
    def __init__(self, base: str, header: str) -> None:
        self.http = httpx.Client(base_url=base, timeout=60)
        self.header = header
        self.key = ""

    def call(self, method: str, path: str, **kwargs) -> httpx.Response:
        headers = {self.header: self.key} if self.key else {}
        resp = self.http.request(method, path, headers=headers, **kwargs)
        if resp.status_code >= 400:
            raise RuntimeError(f"{method} {path} -> {resp.status_code}: {resp.text}")
        return resp

    def create(self, item: dict) -> None:
        self.call("POST", "/passwords/create", json=item)

    def update(self, old: dict, new: dict) -> None:
        self.call(
            "PATCH", "/passwords/update", json={"password": old, "new_password": new}
        )

    def entry_path(self, name: str, suffix: str = "") -> str:
        return f"/passwords/{quote(name, safe='')}{suffix}"


def login(name: str, value: str, **fields: object) -> dict:
    return {"password_name": name, "password_value": value, **fields}


def seed(api: Api, features: set[str]) -> dict:
    created = api.call(
        "POST", "/master_password/create", json={"master_password": FIRST_PASSWORD}
    ).json()
    api.key = created["key_derivation"]

    settings = {
        "inactivity_ms": 300_000,
        "warn_before_ms": 30_000,
        "hidden_ms": 120_000,
        "debounce_ms": 500,
        "clipboard_clear_ms": 15_000,
    }
    if "update_check" in features:
        settings["update_check_enabled"] = False
    api.call("PATCH", "/settings", json=settings)

    modern = "notes" in features
    github = login(
        "GitHub #work",
        "gh-Golden-1",
        username="moth@example.com",
        url="https://github.com/login?next=/",
        totp_secret=(
            "otpauth://totp/GitHub:moth?secret=jbsw y3dp ehpk 3pxp&issuer=GitHub"
        ),
        description="work account",
        tags=["dev", "ops", "2fa"],
        favorite=True,
    )
    if modern:
        github["folder"] = "Work"
        github["custom_fields"] = [
            {"label": "Recovery", "value": "abcd-efgh-ijkl", "hidden": True},
            {"label": "Account ID", "value": "42", "hidden": False},
        ]
    unicode_entry = login(
        "Ünïcode 🦋 名前",
        "пароль-🦋-パス",
        username="мотылёк@пример.рф",
        url="https://例え.テスト/",
        description="RTL: סיסמה",
        tags=["ключ", "タグ"],
    )
    history = login("history", "h-00")
    entries = [
        github,
        unicode_entry,
        login(
            "whitespace",
            "  spaced value\t\n",
            description="  padded description  ",
        ),
        login("reserved #?%/& chars", "reserved-Value-1"),
        history,
        login(
            "tagged-max",
            "tags-Value-1",
            tags=[f"{i:02d}" + "t" * 38 for i in range(20)],
        ),
        login(
            "max-" + "n" * 251,
            "v" * 4096,
            username="u" * 255,
            url="https://" + "u" * 2040,
            description="d" * 1024,
        ),
    ]
    if modern:
        entries += [
            login(
                "Recovery codes",
                "code-1\ncode-2\n\n  indented\n",
                kind="note",
                folder="Security",
            ),
            login(
                "custom-max",
                "custom-Value-1",
                custom_fields=[
                    {
                        "label": f"{i:02d}" + "l" * 98,
                        "value": "x" * 4096 if i == 0 else f"value {i}",
                        "hidden": i % 2 == 0,
                    }
                    for i in range(30)
                ],
            ),
            login("trashed-only", "trashed-Value-1", folder="Old"),
        ]
    for item in entries:
        api.create(item)

    current = history
    for step in range(1, 13):
        changed = {**current, "password_value": f"h-{step:02d}"}
        api.update(current, changed)
        current = changed

    attachments = {}
    if "attachments" in features:
        attachments = {
            "GitHub #work": [
                ("scan.bin", rng_bytes("scan", 16 * 1024), "application/octet-stream"),
                (
                    "Preț ✓.pdf",
                    b"%PDF-1.4\n" + rng_bytes("pdf", 512),
                    "application/pdf",
                ),
            ],
            "trashed-only": [
                ("old.bin", rng_bytes("old", 256), "application/octet-stream")
            ],
        }
        for name, files in attachments.items():
            for filename, data, content_type in files:
                api.call(
                    "POST",
                    api.entry_path(name, "/attachments"),
                    files={"file": (filename, data, content_type)},
                )

    api.call(
        "PATCH",
        "/master_password/update",
        json={"master_password": FIRST_PASSWORD, "new_master_password": FINAL_PASSWORD},
    )
    api.key = ""
    checked = api.call(
        "POST", "/master_password/check", json={"master_password": FINAL_PASSWORD}
    ).json()
    api.key = checked["key_derivation"]

    api.create(login("post-rotation", "after-Rotation-1", username="late"))
    api.call(
        "PATCH", api.entry_path("Ünïcode 🦋 名前", "/favorite"), json={"favorite": True}
    )
    if "attachments" in features:
        late = (
            "after-rotation.txt",
            b"added after the rotation\n",
            "text/plain",
        )
        attachments["Recovery codes"] = [late]
        api.call(
            "POST",
            api.entry_path("Recovery codes", "/attachments"),
            files={"file": late},
        )
    if "trash" in features:
        api.call("DELETE", api.entry_path("trashed-only"))
        api.create(login("dup", "dup-Old-1"))
        api.call("DELETE", api.entry_path("dup"))
        api.create(login("dup", "dup-New-2"))

    backup = api.call(
        "POST", "/passwords/backup", json={"master_password": FINAL_PASSWORD}
    ).content
    post = login("post-rotation", "after-Rotation-1", username="late")
    api.update(post, {**post, "description": "edited after the backup"})

    return {"backup": backup, "attachments": attachments}


def read_back(api: Api, features: set[str], attachments: dict) -> dict:
    key = api.key
    api.key = ""
    spaced = api.call(
        "POST",
        "/master_password/check",
        json={"master_password": f"  {FINAL_PASSWORD}  "},
    ).json()
    assert spaced["key_derivation"] == key, "surrounding whitespace changed the key"
    api.key = key

    expected: dict = {
        "key": key,
        "settings": api.call("GET", "/settings").json(),
        "active": api.call("GET", "/passwords").json(),
        "trash": api.call("GET", "/passwords/trash").json()
        if "trash" in features
        else [],
        "attachments": {},
    }
    if "attachments" in features:
        trashed = {item["password_name"] for item in expected["trash"]}
        for name, files in attachments.items():
            listed = (
                []
                if name in trashed
                else api.call("GET", api.entry_path(name, "/attachments")).json()
            )
            records = []
            for filename, data, content_type in files:
                record = {
                    "filename": filename,
                    "content_type": content_type,
                    "size_bytes": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                }
                for item in listed:
                    if item["filename"] == filename:
                        downloaded = api.call(
                            "GET", api.entry_path(name, f"/attachments/{item['id']}")
                        ).content
                        assert downloaded == data, f"{name}/{filename} round trip"
                records.append(record)
            expected["attachments"][name] = records
    return expected


def pg_dump(db_container: str) -> tuple[str, str]:
    dump = run(
        "docker",
        "exec",
        db_container,
        "pg_dump",
        "-U",
        DB_USER,
        "-d",
        DB_NAME,
        "--column-inserts",
        "--no-owner",
        "--no-privileges",
        "--no-comments",
    ).stdout
    lines = [line for line in dump.splitlines() if not line.startswith("\\")]
    revision = run(
        "docker",
        "exec",
        db_container,
        "psql",
        "-U",
        DB_USER,
        "-d",
        DB_NAME,
        "-Atc",
        "SELECT version_num FROM alembic_version",
    ).stdout.strip()
    return "\n".join(lines) + "\n", revision


def generate(release: str, force: bool) -> None:
    spec = RELEASES[release]
    target = OUT / release
    if target.exists() and not force:
        raise SystemExit(f"{target} exists; golden fixtures are frozen (use --force)")
    features = spec["features"]
    image, provenance = image_for(release, spec)
    suffix = f"{release.replace('.', '-')}-{int(time.time())}"
    network = f"ciphermoth-golden-{suffix}"
    db = f"ciphermoth-golden-db-{suffix}"
    api_container = f"ciphermoth-golden-api-{suffix}"
    port = free_port()
    env = {
        "POSTGRES_HOST": db,
        "POSTGRES_PORT": "5432",
        "POSTGRES_DB": DB_NAME,
        "POSTGRES_USER": DB_USER,
        "POSTGRES_PASSWORD": DB_PASSWORD,
        spec.get("rate_env", "CIPHERMOTH_RATE_LIMIT"): "100000/hour",
    }
    try:
        run("docker", "network", "create", network)
        run(
            "docker",
            "run",
            "-d",
            "--name",
            db,
            "--network",
            network,
            "--tmpfs",
            "/var/lib/postgresql/data",
            "-e",
            f"POSTGRES_USER={DB_USER}",
            "-e",
            f"POSTGRES_PASSWORD={DB_PASSWORD}",
            "-e",
            f"POSTGRES_DB={DB_NAME}",
            "postgres:16-alpine",
        )
        for _ in range(60):
            ready = subprocess.run(
                ["docker", "exec", db, "pg_isready", "-U", DB_USER, "-d", DB_NAME],
                capture_output=True,
            )
            if ready.returncode == 0:
                break
            time.sleep(1)
        time.sleep(2)
        env_args = [arg for k, v in env.items() for arg in ("-e", f"{k}={v}")]
        run(
            "docker",
            "run",
            "-d",
            "--name",
            api_container,
            "--network",
            network,
            "-p",
            f"127.0.0.1:{port}:80",
            *env_args,
            image,
        )
        base = f"http://127.0.0.1:{port}/api"
        for _ in range(120):
            try:
                if httpx.get(f"{base}/master_password/status", timeout=2).is_success:
                    break
            except httpx.TransportError:
                pass
            time.sleep(1)
        else:
            logs = run("docker", "logs", api_container).stdout
            raise RuntimeError(f"{release} did not start:\n{logs}")

        api = Api(base, spec.get("header", "x-ciphermoth-key-derivation"))
        seeded = seed(api, features)
        expected = read_back(api, features, seeded["attachments"])
        dump, revision = pg_dump(db)
    finally:
        for name in (api_container, db):
            subprocess.run(["docker", "rm", "-f", name], capture_output=True)
        subprocess.run(["docker", "network", "rm", network], capture_output=True)

    target.mkdir(parents=True, exist_ok=True)
    (target / "dump.sql").write_text(dump)
    (target / "backup.zip").write_bytes(seeded["backup"])
    manifest = {
        "format": "ciphermoth-golden/1",
        "release": release,
        "image": image,
        "provenance": provenance,
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "alembic_revision": revision,
        "features": sorted(features),
        "key_header": api.header,
        "master_password": FINAL_PASSWORD,
        "previous_master_password": FIRST_PASSWORD,
        "dump_sha256": hashlib.sha256(dump.encode()).hexdigest(),
        "backup_sha256": hashlib.sha256(seeded["backup"]).hexdigest(),
        **expected,
    }
    (target / "expected.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    )
    print(f"{release}: revision {revision}, {len(dump)} bytes of SQL")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("releases", nargs="+", choices=sorted(RELEASES))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    for release in args.releases:
        generate(release, args.force)
    return 0


if __name__ == "__main__":
    sys.exit(main())
