import asyncio
import json
import subprocess
import sys
from datetime import datetime
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
    updater_alive,
)
from tests.support import update_control_dir as control_dir
from tests.updater_harness import UPDATER, World, stale_time
from update_protocol import RECREATE_UPDATER_COMMAND

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
    updater_alive()

    resp = await _apply(client, key, target)

    assert resp.status_code == 403, resp.text
    assert "newer" in resp.json()["detail"]
    assert control_files() == ["updater.json"]


@pytest.mark.parametrize(
    "target",
    ["latest", "1.9.9", "v1.9", "v1.9.9-rc1", "v1.9.9\n", "v1.9.9;id", "v٩.٩.٩"],
)
async def test_apply_refuses_malformed_targets(
    client: httpx.AsyncClient, target: str
) -> None:
    key = await create_vault(client)
    updater_alive()

    resp = await _apply(client, key, target)

    assert resp.status_code in (403, 422), resp.text
    assert control_files() == ["updater.json"]


async def test_apply_accepts_a_newer_release(client: httpx.AsyncClient) -> None:
    key = await create_vault(client)
    updater_alive()
    major, minor, _ = CURRENT.split(".")
    for target in (bump_patch(CURRENT), f"v{major}.{int(minor) + 1}.0"):
        (control_dir() / "request.json").unlink(missing_ok=True)
        resp = await _apply(client, key, target)
        assert resp.status_code == 200, resp.text
        request = json.loads((control_dir() / "request.json").read_text())
        assert request["target"] == target
        assert request["id"] == resp.json()["request_id"]
        assert len(request["id"]) == 32
        assert datetime.fromisoformat(request["requested_at"]).tzinfo is not None
        assert resp.json()["state"] == "requested"


async def test_apply_requires_the_updater_sidecar(client: httpx.AsyncClient) -> None:
    key = await create_vault(client)
    resp = await _apply(client, key, bump_patch(CURRENT))
    assert resp.status_code == 403
    assert "not enabled" in resp.json()["detail"]
    assert control_files() == []


async def test_an_old_updater_must_be_recreated_before_one_click_updates(
    client: httpx.AsyncClient,
) -> None:
    key = await create_vault(client)
    (control_dir() / "updater.ready").touch()

    status = (await client.get("/updates/apply/status")).json()
    resp = await _apply(client, key, bump_patch(CURRENT))

    assert status["updater_present"] is True
    assert status["updater_protocol"] == 1
    assert status["updater_upgrade_required"] is True
    assert status["required_protocol"] == 2
    assert resp.status_code == 403
    assert RECREATE_UPDATER_COMMAND in resp.json()["detail"]
    assert control_files() == ["updater.ready"]


@pytest.mark.parametrize(
    ("age", "running"), [(300, True), (0, False)], ids=["silent", "stopped"]
)
async def test_an_updater_that_is_not_running_is_reported(
    client: httpx.AsyncClient, age: int, running: bool
) -> None:
    key = await create_vault(client)
    updater_alive(age=age, running=running)
    (control_dir() / "updater.ready").touch()

    status = (await client.get("/updates/apply/status")).json()
    resp = await _apply(client, key, bump_patch(CURRENT))

    assert status["updater_present"] is False
    assert status["updater_protocol"] == 2
    assert status["updater_upgrade_required"] is False
    assert resp.status_code == 403
    assert "not running" in resp.json()["detail"]
    assert "request.json" not in control_files()


async def test_a_second_request_is_refused_while_one_waits(
    client: httpx.AsyncClient,
) -> None:
    key = await create_vault(client)
    updater_alive()
    assert (await _apply(client, key, bump_patch(CURRENT))).status_code == 200
    first = (control_dir() / "request.json").read_text()

    resp = await _apply(client, key, bump_patch(CURRENT, 2))

    assert resp.status_code == 403
    assert "already" in resp.json()["detail"]
    assert (control_dir() / "request.json").read_text() == first


async def test_concurrent_requests_publish_exactly_one(
    client: httpx.AsyncClient,
) -> None:
    key = await create_vault(client)
    updater_alive()

    responses = await asyncio.gather(
        *(_apply(client, key, bump_patch(CURRENT, n)) for n in range(1, 6))
    )

    assert sorted(r.status_code for r in responses).count(200) == 1
    accepted = next(r for r in responses if r.status_code == 200).json()
    request = json.loads((control_dir() / "request.json").read_text())
    assert request["id"] == accepted["request_id"]


@pytest.mark.parametrize(
    "state", ["verifying", "snapshotting", "applying", "validating", "rolling_back"]
)
async def test_requests_are_refused_while_an_update_runs(
    client: httpx.AsyncClient, state: str
) -> None:
    key = await create_vault(client)
    updater_alive()
    (control_dir() / "result.json").write_text(json.dumps({"state": state}))

    resp = await _apply(client, key, bump_patch(CURRENT))

    assert resp.status_code == 403
    assert "in progress" in resp.json()["detail"]
    assert (await client.get("/updates/apply/status")).json()["state"] == state


async def test_requests_are_refused_when_an_update_needs_attention(
    client: httpx.AsyncClient,
) -> None:
    key = await create_vault(client)
    updater_alive()
    (control_dir() / "result.json").write_text(
        json.dumps({"state": "intervention", "detail": "restore failed"})
    )

    resp = await _apply(client, key, bump_patch(CURRENT))

    assert resp.status_code == 403
    assert "manual attention" in resp.json()["detail"]
    status = (await client.get("/updates/apply/status")).json()
    assert status["state"] == "intervention"
    assert status["detail"] == "restore failed"


async def test_status_reports_the_updater_and_maintenance(
    client: httpx.AsyncClient,
) -> None:
    updater_alive()
    (control_dir() / "result.json").write_text(
        json.dumps({"state": "validating", "target": "v9.9.9", "id": "a" * 32})
    )
    (control_dir() / "maintenance.json").write_text("{}")

    status = (await client.get("/updates/apply/status")).json()

    assert status == {
        "state": "validating",
        "detail": None,
        "target": "v9.9.9",
        "finished_at": None,
        "id": "a" * 32,
        "request_id": None,
        "updater_present": True,
        "updater_protocol": 2,
        "updater_version": "1.5.1",
        "updater_upgrade_required": False,
        "required_protocol": 2,
        "maintenance": True,
    }


def _updater_newer(candidate: str, current: str) -> bool:
    proc = subprocess.run(
        [sys.executable, str(UPDATER), "newer", candidate, current],
        capture_output=True,
        timeout=30,
    )
    return proc.returncode == 0


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
        ("v٩.٩.٩", "1.0.0", False),
    ],
)
def test_updater_version_comparison(candidate: str, current: str, newer: bool) -> None:
    assert _updater_newer(candidate, current) is newer


def _changes(world: World) -> list[str]:
    return [
        line
        for line in world.calls
        if line.startswith(("docker", "cosign", "pg_dump", "pg_restore"))
    ]


@pytest.mark.parametrize(
    ("target", "fields", "reason"),
    [
        ("v1.5.0", {}, "not newer than the running version 1.5.1"),
        ("v1.5.1", {}, "not newer than the running version 1.5.1"),
        ("latest", {}, "not a release tag"),
        ("v1.5.2;touch /tmp/x", {}, "not a release tag"),
        ("v1.5.2\n", {}, "not a release tag"),
        ("v1.5.2", {"id": "../../etc"}, "invalid id"),
        ("v1.5.2", {"requested_at": stale_time(60)}, "expired"),
        ("v1.5.2", {"requested_at": "yesterday"}, "invalid time"),
    ],
    ids=[
        "older",
        "same",
        "latest",
        "injection",
        "newline",
        "bad-id",
        "expired",
        "bad-time",
    ],
)
def test_updater_refuses_before_pulling_anything(
    tmp_path: Path, target: str, fields: dict, reason: str
) -> None:
    world = World(tmp_path)
    world.release("1.5.2")
    world.request(target, **fields)

    world.run()

    assert world.result["state"] == "failed", world.log
    assert reason in world.result["detail"]
    assert "Nothing was changed" in world.result["detail"]
    assert _changes(world) == []
    assert world.env_version == "1.5.1"
    assert not (world.control / "request.json").exists()
    assert world.maintenance is None


def test_updater_refuses_when_the_running_version_is_unknown(tmp_path: Path) -> None:
    world = World(tmp_path)
    world.flag("backend_health_fail")
    world.state["original_version"] = "none"
    world.save()
    world.request("v1.5.2")

    world.run()

    assert world.result["state"] == "failed"
    assert "not answering" in world.result["detail"]
    assert _changes(world) == []


def test_updater_still_requires_a_valid_signature_for_newer_targets(
    tmp_path: Path,
) -> None:
    world = World(tmp_path)
    world.release("1.5.2", signed=False)
    world.request("v1.5.2")

    world.run()

    assert world.result["state"] == "failed"
    assert "signature" in world.result["detail"]
    assert any(line.startswith("docker pull") for line in world.calls)
    assert any(line.startswith("cosign verify") for line in world.calls)
    assert not [line for line in world.calls if "compose" in line and " up " in line]
    assert not [line for line in world.calls if line.startswith("pg_dump")]
    assert world.env_version == "1.5.1"
    assert world.running() == "1.5.1"


def test_updater_success_verifies_snapshots_then_applies(tmp_path: Path) -> None:
    world = World(tmp_path)
    world.release("1.5.2")
    before = world.live_db
    world.request("v1.5.2")

    world.run()

    assert world.result["state"] == "success", world.log
    assert world.env_version == "1.5.2"
    assert world.running() == "1.5.2"
    assert world.running("frontend") == "1.5.2"
    assert "OTHER=kept" in world.env_file.read_text()
    assert oct(world.env_file.stat().st_mode & 0o777) == oct(0o640)
    calls = world.calls
    signatures = [i for i, line in enumerate(calls) if line.startswith("cosign")]
    assert len(signatures) == 4
    stop = world.index("docker compose") and next(
        i for i, line in enumerate(calls) if " stop backend" in line
    )
    dump = world.index("pg_dump")
    verify = next(i for i, line in enumerate(calls) if "_verify_" in line)
    up = next(i for i, line in enumerate(calls) if " up -d " in line)
    assert max(signatures) < stop < dump < verify < up
    assert world.live_db == before
    assert world.journal["phase"] == "committed"
    assert world.maintenance is None
    names = world.snapshots
    assert len([n for n in names if n.endswith(".dump")]) == 1
    assert len([n for n in names if n.endswith(".json")]) == 1
    assert not [n for n in names if n.endswith(".partial")]
    assert world.database_names == ["ciphermoth"]
    assert world.secrets_leaked() == []
    assert not list((world.backups / "state" / "updates").iterdir())


CONTRACT = "Updater safety contract (CONTRIBUTING.md, 'Schema changes and the updater')"


def test_contract_no_update_without_a_restorable_snapshot(tmp_path: Path) -> None:
    world = World(tmp_path)
    world.release("1.5.2")
    world.flag("dump_fail")
    before = world.live_db
    world.request("v1.5.2")

    world.run()

    assert world.result["state"] == "failed", CONTRACT
    assert not [line for line in world.calls if " up -d " in line]
    assert world.env_version == "1.5.1"
    assert world.running() == "1.5.1"
    assert world.live_db == before
    assert world.maintenance is None
    assert not [n for n in world.snapshots if n.endswith((".dump", ".partial"))]


def test_contract_rollback_restores_the_pre_update_snapshot(tmp_path: Path) -> None:
    world = World(tmp_path)
    world.release("1.5.2", migrate_to="rev2")
    world.flag("backend_health_fail")
    before = world.live_db
    world.request("v1.5.2")

    world.run()

    calls = world.calls
    restores = [
        i
        for i, line in enumerate(calls)
        if line.startswith(("psql", "pg_restore")) and str(world.backups) in line
    ]
    ups = [i for i, line in enumerate(calls) if " up -d " in line]
    assert len(ups) == 2, CONTRACT
    assert restores and restores[0] < ups[1]
    rollback_restores = [
        i
        for i, line in enumerate(calls)
        if line.startswith("pg_restore") and "_restore_" in line
    ]
    assert rollback_restores and ups[0] < rollback_restores[0] < ups[1]
    assert world.result["state"] == "rolled_back", world.log
    assert world.live_db == before
    assert world.running() == "1.5.1"
    assert world.env_version == "1.5.1"
    assert world.maintenance is None
    assert world.database_names == ["ciphermoth"]


def test_contract_an_interrupted_update_is_reconciled_on_restart(
    tmp_path: Path,
) -> None:
    world = World(tmp_path)
    world.release("1.5.2", migrate_to="rev2")
    before = world.live_db
    world.flag("kill_on_up")
    world.request("v1.5.2")
    world.run()
    assert world.process is not None and world.process.returncode != 0
    assert world.journal["phase"] == "applying"
    assert world.env_version == "1.5.2"
    assert world.maintenance is not None

    world.unflag("kill_on_up")
    world.request("v0.0.0")
    world.serve_for(8)

    assert world.result["state"] in ("failed", "rolled_back", "success"), CONTRACT
    assert world.env_version == world.running()
    assert world.journal["phase"] == "rolled_back"
    assert world.running() == "1.5.1"
    assert world.live_db == before
    assert world.maintenance is None


def test_contract_the_updater_updates_itself(tmp_path: Path) -> None:
    world = World(tmp_path)
    world.release("1.5.2")
    world.request("v1.5.2")

    world.run(CIPHERMOTH_UPDATER_VERSION="1.5.1")

    assert world.result["state"] == "success"
    detail = world.result["detail"]
    assert "updater" in detail.lower(), CONTRACT
    assert "--profile autoupdate pull updater" in detail
    assert world.result["action"] == "recreate-updater"
    heartbeat = json.loads((world.control / "updater.json").read_text())
    assert heartbeat["protocol"] == 2
    assert heartbeat["version"] == "1.5.1"
