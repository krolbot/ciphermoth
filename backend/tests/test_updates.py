import json
import os
import shutil
import subprocess
from pathlib import Path

import httpx
import pytest

from settings import get_api_settings
from tests.support import auth, bump_patch, control_files, create_vault
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
        bump_patch(CURRENT, -1),
        "v0.0.1",
        "v1.0.0",
    ],
    ids=["same", "previous-patch", "ancient", "older-major"],
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
