import json
import os
import shutil
import subprocess
from pathlib import Path

import httpx
import pytest

from settings import get_api_settings
from tests.support import (
    auth,
    bump_patch,
    control_files,
    create_vault,
    previous_version,
)
from tests.support import update_control_dir as control_dir

UPDATER = Path(__file__).resolve().parents[2] / "docker" / "updater" / "updater.sh"
CURRENT = get_api_settings().version


async def _apply(client: httpx.AsyncClient, key: str, target: str) -> httpx.Response:
    return await client.post(
        "/updates/apply", json={"target": target}, headers=auth(key)
    )


@pytest.mark.parametrize(
    "target",
    [
        f"v{CURRENT}",
        previous_version(CURRENT),
        "v0.0.1",
        "v1.0.0",
    ],
    ids=["same", "previous", "ancient", "older-major"],
)
async def test_apply_refuses_targets_that_are_not_newer(
    client: httpx.AsyncClient, target: str
) -> None:
    key = await create_vault(client)
    (control_dir() / "updater.ready").touch()

    resp = await _apply(client, key, target)

    assert resp.status_code == 403, resp.text
    assert "newer" in resp.json()["detail"]
    assert control_files() == ["updater.ready"]


@pytest.mark.parametrize(
    "target",
    ["latest", "1.9.9", "v1.9", "v1.9.9-rc1", "v1.9.9\n", "v1.9.9;id", "v٩.٩.٩"],
)
async def test_apply_refuses_malformed_targets(
    client: httpx.AsyncClient, target: str
) -> None:
    key = await create_vault(client)
    (control_dir() / "updater.ready").touch()

    resp = await _apply(client, key, target)

    assert resp.status_code in (403, 422), resp.text
    assert control_files() == ["updater.ready"]


async def test_apply_accepts_a_newer_release(client: httpx.AsyncClient) -> None:
    key = await create_vault(client)
    (control_dir() / "updater.ready").touch()
    major, minor, _ = CURRENT.split(".")
    for target in (bump_patch(CURRENT), f"v{major}.{int(minor) + 1}.0"):
        resp = await _apply(client, key, target)
        assert resp.status_code == 200, resp.text
        request = json.loads((control_dir() / "request.json").read_text())
        assert request["target"] == target


async def test_apply_requires_the_updater_sidecar(client: httpx.AsyncClient) -> None:
    key = await create_vault(client)
    resp = await _apply(client, key, bump_patch(CURRENT))
    assert resp.status_code == 403
    assert control_files() == []


needs_shell_tools = pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("jq") is None,
    reason="updater.sh tests need bash and jq",
)


def _source(snippet: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", f'source "{UPDATER}"\n{snippet}'],
        capture_output=True,
        text=True,
        timeout=30,
    )


@needs_shell_tools
@pytest.mark.parametrize(
    ("candidate", "current", "newer"),
    [
        ("v1.4.6", "1.4.5", True),
        ("v1.5.0", "1.4.9", True),
        ("v2.0.0", "1.99.99", True),
        ("v1.4.10", "1.4.9", True),
        ("v1.4.5", "1.4.5", False),
        ("v1.4.4", "1.4.5", False),
        ("v1.3.99", "1.4.0", False),
        ("v0.9.9", "1.0.0", False),
        ("v1.4.6-rc1", "1.4.5", False),
        ("latest", "1.4.5", False),
        ("v1.4.6", "", False),
        ("v1.4.6", "latest", False),
        ("v08.0.0", "7.0.0", True),
    ],
)
async def test_updater_version_comparison(
    candidate: str, current: str, newer: bool
) -> None:
    result = _source(f'version_is_newer "{candidate}" "{current}"')
    assert (result.returncode == 0) is newer, result.stderr


def _stub(bin_dir: Path, name: str, body: str) -> None:
    path = bin_dir / name
    path.write_text(f"#!/bin/sh\n{body}\n")
    path.chmod(0o755)


def _run_request(tmp_path: Path, target: str, running: str, cosign_ok: bool) -> dict:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "calls.log"
    calls.touch()
    control = tmp_path / "control"
    control.mkdir()
    env_file = tmp_path / ".env"
    env_file.write_text("POSTGRES_PASSWORD=x\nCIPHERMOTH_VERSION=1.4.5\n")
    _stub(bin_dir, "docker", f'echo "docker $*" >> "{calls}"\necho "repo@sha256:0"')
    _stub(
        bin_dir,
        "cosign",
        f'echo "cosign $*" >> "{calls}"\nexit {0 if cosign_ok else 1}',
    )
    _stub(bin_dir, "pg_dump", f'echo "pg_dump" >> "{calls}"')
    _stub(bin_dir, "curl", f"echo '{json.dumps({'version': running})}'")
    (control / "request.json").write_text(json.dumps({"target": target}))

    result = subprocess.run(
        ["bash", "-c", f'source "{UPDATER}"\nprocess_request'],
        capture_output=True,
        text=True,
        timeout=60,
        env={
            **os.environ,
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "UPDATE_CONTROL_DIR": str(control),
            "ENV_FILE": str(env_file),
            "BACKUP_DIR": str(tmp_path / "backups"),
            "HEALTH_RETRIES": "1",
            "HEALTH_INTERVAL": "0",
        },
    )
    assert result.returncode == 0, result.stderr
    return {
        "result": json.loads((control / "result.json").read_text()),
        "calls": calls.read_text(),
        "env": env_file.read_text(),
        "request_left": (control / "request.json").exists(),
    }


@needs_shell_tools
@pytest.mark.parametrize(
    ("target", "running"),
    [
        ("v1.4.4", "1.4.5"),
        ("v1.4.5", "1.4.5"),
        ("v1.4.6", ""),
        ("v1.4.6", "garbage"),
        ("latest", "1.4.5"),
        ("v1.4.6;touch /tmp/x", "1.4.5"),
    ],
    ids=["older", "same", "unknown-current", "bad-current", "latest", "injection"],
)
async def test_updater_refuses_before_pulling_anything(
    tmp_path: Path, target: str, running: str
) -> None:
    outcome = _run_request(tmp_path, target, running, cosign_ok=True)

    assert outcome["result"]["state"] == "failed"
    assert "Nothing was changed" in outcome["result"]["detail"]
    assert outcome["calls"] == ""
    assert "CIPHERMOTH_VERSION=1.4.5" in outcome["env"]
    assert not outcome["request_left"]


@needs_shell_tools
async def test_updater_still_requires_a_valid_signature_for_newer_targets(
    tmp_path: Path,
) -> None:
    outcome = _run_request(tmp_path, "v1.4.6", "1.4.5", cosign_ok=False)

    assert outcome["result"]["state"] == "failed"
    assert "docker pull" in outcome["calls"]
    assert "cosign verify" in outcome["calls"]
    assert "compose" not in outcome["calls"]
    assert "pg_dump" not in outcome["calls"]
    assert "CIPHERMOTH_VERSION=1.4.5" in outcome["env"]


_GNU_SED_IN_PLACE = """#!/usr/bin/env python3
import os
import re
import sys

if sys.argv[1] != "-i":
    os.execv("/usr/bin/sed", ["sed", *sys.argv[1:]])
expression, path = sys.argv[2], sys.argv[3]
_, pattern, replacement, _ = expression.split(expression[1])
with open(path) as handle:
    text = handle.read()
with open(path, "w") as handle:
    handle.write(re.sub(pattern, replacement, text, flags=re.M))
"""


class _UpdaterRun:
    def __init__(self, tmp_path: Path, running: str = "1.4.6") -> None:
        self.root = tmp_path
        self.bin = tmp_path / "bin"
        self.state = tmp_path / "state"
        self.control = tmp_path / "control"
        self.backups = tmp_path / "backups"
        for directory in (self.bin, self.state, self.control):
            directory.mkdir()
        self.calls = tmp_path / "calls.log"
        self.calls.touch()
        self.env_file = tmp_path / ".env"
        self.env_file.write_text(
            f"POSTGRES_PASSWORD=x\nCIPHERMOTH_VERSION={running}\nOTHER=kept\n"
        )
        (self.state / "running").write_text(running)
        log = f'echo "$(basename "$0") $*" >> "{self.calls}"'
        _stub(
            self.bin,
            "docker",
            f"{log}\n"
            'case "$*" in\n'
            '  *inspect*) echo "repo@sha256:0" ;;\n'
            "  *compose*up*)\n"
            f'    version="$(grep ^CIPHERMOTH_VERSION= "{self.env_file}" '
            '| cut -d= -f2)"\n'
            f'    if [ -f "{self.state}/up_fail" ] && '
            f'[ "$version" != "$(cat "{self.state}/original")" ]; then exit 1; fi\n'
            f'    if [ -f "{self.state}/kill_on_up" ]; then '
            "kill -KILL $PPID; exit 1; fi\n"
            f'    echo "$version" > "{self.state}/running" ;;\n'
            "esac\n",
        )
        _stub(self.bin, "cosign", log)
        _stub(
            self.bin,
            "pg_dump",
            f'{log}\nif [ -f "{self.state}/dump_fail" ]; then exit 1; fi\n'
            'while [ $# -gt 0 ]; do [ "$1" = "-f" ] && echo "-- dump" > "$2"; '
            "shift; done",
        )
        for name in ("psql", "pg_restore"):
            _stub(self.bin, name, log)
        if subprocess.run(["sed", "--version"], capture_output=True).returncode:
            sed = self.bin / "sed"
            sed.write_text(_GNU_SED_IN_PLACE)
            sed.chmod(0o755)
        _stub(
            self.bin,
            "curl",
            f'running="$(cat "{self.state}/running")"\n'
            f'if [ -f "{self.state}/health_fail" ] && '
            f'[ "$running" != "$(cat "{self.state}/original")" ]; then exit 22; fi\n'
            'echo "{\\"version\\": \\"$running\\"}"',
        )
        (self.state / "original").write_text(running)

    def flag(self, name: str) -> None:
        (self.state / name).touch()

    def run(self, target: str, snippet: str = "process_request") -> None:
        (self.control / "request.json").write_text(json.dumps({"target": target}))
        self.process = subprocess.run(
            ["bash", "-c", f'source "{UPDATER}"\n{snippet}'],
            capture_output=True,
            text=True,
            timeout=60,
            env={
                **os.environ,
                "PATH": f"{self.bin}:{os.environ['PATH']}",
                "UPDATE_CONTROL_DIR": str(self.control),
                "ENV_FILE": str(self.env_file),
                "BACKUP_DIR": str(self.backups),
                "HEALTH_RETRIES": "1",
                "HEALTH_INTERVAL": "0",
                "POLL_INTERVAL": "0",
            },
        )

    @property
    def result(self) -> dict:
        return json.loads((self.control / "result.json").read_text())

    @property
    def lines(self) -> list[str]:
        return self.calls.read_text().splitlines()

    @property
    def env_version(self) -> str:
        for line in self.env_file.read_text().splitlines():
            if line.startswith("CIPHERMOTH_VERSION="):
                return line.split("=", 1)[1]
        return ""

    @property
    def running(self) -> str:
        return (self.state / "running").read_text().strip()

    def index(self, prefix: str) -> int:
        return next(i for i, line in enumerate(self.lines) if line.startswith(prefix))


@needs_shell_tools
async def test_updater_success_verifies_snapshots_then_applies(tmp_path: Path) -> None:
    run = _UpdaterRun(tmp_path)

    run.run("v1.4.7")

    assert run.result["state"] == "success", run.process.stderr
    assert run.env_version == "1.4.7"
    assert run.running == "1.4.7"
    assert "OTHER=kept" in run.env_file.read_text()
    verified = max(i for i, line in enumerate(run.lines) if line.startswith("cosign"))
    assert verified < run.index("pg_dump") < run.index("docker compose")
    assert len([line for line in run.lines if line.startswith("cosign")]) == 2
    assert list(run.backups.glob("*.sql"))


@needs_shell_tools
@pytest.mark.parametrize("failure", ["up_fail", "health_fail"])
async def test_updater_rolls_back_to_the_previous_images(
    tmp_path: Path, failure: str
) -> None:
    run = _UpdaterRun(tmp_path)
    run.flag(failure)

    run.run("v1.4.7")

    assert run.result["state"] == "rolled_back", run.process.stderr
    assert run.result["target"] == "1.4.6"
    assert run.env_version == "1.4.6"
    assert run.running == "1.4.6"
    assert "OTHER=kept" in run.env_file.read_text()
    assert len([line for line in run.lines if " up -d " in line]) == 2


CONTRACT = (
    "Updater safety contract, required before any release adds an Alembic "
    "revision (see CONTRIBUTING.md, 'Schema changes and the updater')"
)


@needs_shell_tools
@pytest.mark.xfail(strict=True, reason=CONTRACT)
async def test_contract_no_update_without_a_restorable_snapshot(tmp_path: Path) -> None:
    run = _UpdaterRun(tmp_path)
    run.flag("dump_fail")

    run.run("v1.4.7")

    assert run.result["state"] == "failed"
    assert not [line for line in run.lines if " up -d " in line]
    assert run.env_version == "1.4.6"


@needs_shell_tools
@pytest.mark.xfail(strict=True, reason=CONTRACT)
async def test_contract_rollback_restores_the_pre_update_snapshot(
    tmp_path: Path,
) -> None:
    run = _UpdaterRun(tmp_path)
    run.flag("health_fail")

    run.run("v1.4.7")

    restores = [
        i
        for i, line in enumerate(run.lines)
        if line.startswith(("psql", "pg_restore")) and str(run.backups) in line
    ]
    second_up = [i for i, line in enumerate(run.lines) if " up -d " in line][1]
    assert restores and restores[0] < second_up


@needs_shell_tools
@pytest.mark.xfail(strict=True, reason=CONTRACT)
async def test_contract_an_interrupted_update_is_reconciled_on_restart(
    tmp_path: Path,
) -> None:
    run = _UpdaterRun(tmp_path)
    run.flag("kill_on_up")
    run.run("v1.4.7")
    assert run.running == "1.4.6"

    (run.state / "kill_on_up").unlink()
    run.run("v0.0.0", snippet="timeout 5 bash -c 'source \"$0\"; main' " + str(UPDATER))

    assert run.result["state"] in ("failed", "rolled_back", "success")
    assert run.env_version == run.running


@needs_shell_tools
@pytest.mark.xfail(strict=True, reason=CONTRACT)
async def test_contract_the_updater_updates_itself(tmp_path: Path) -> None:
    run = _UpdaterRun(tmp_path)

    run.run("v1.4.7")

    services = [
        line.split(" up -d ", 1)[1].split() for line in run.lines if " up -d " in line
    ]
    assert (
        any("updater" in names for names in services)
        or "updater" in run.result["detail"].lower()
    )
