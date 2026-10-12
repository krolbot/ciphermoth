import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from tests.updater_harness import UPDATER, World, initial_database

BEFORE_APPLYING = [
    "verified",
    "maintenance_on",
    "backend_stopped",
    "snapshot_dumped",
    "snapshot_verified",
    "snapshot_committed",
]
WHILE_APPLYING = ["env_written", "compose_up_done", "validated"]
ROLLBACK_POINTS = [
    "rollback_stopped",
    "restore_created",
    "restore_swapped",
    "rollback_env",
    "rollback_started",
]


def _converged(world: World) -> None:
    assert world.journal["phase"] in ("committed", "rolled_back", "failed"), world.log
    assert world.maintenance is None
    assert world.env_version == world.running()
    assert world.running("frontend") == world.running()
    assert world.database_names == ["ciphermoth"]
    assert not [n for n in world.snapshots if n.endswith(".partial")]
    assert not list((world.backups / "state" / "updates").iterdir())


def _killed(world: World) -> None:
    assert world.process is not None
    assert world.process.returncode == -9, world.log


@pytest.mark.parametrize("point", BEFORE_APPLYING)
def test_a_crash_before_applying_changes_nothing(tmp_path: Path, point: str) -> None:
    world = World(tmp_path)
    world.release("1.5.2", migrate_to="rev2")
    before = world.live_db
    world.request("v1.5.2")

    world.run(CIPHERMOTH_UPDATER_FAULT=f"kill:{point}")
    _killed(world)
    world.run()

    _converged(world)
    assert world.journal["phase"] == "failed"
    assert world.result["state"] == "failed"
    assert "Nothing was changed" in world.result["detail"]
    assert world.running() == "1.5.1"
    assert world.live_db == before
    assert not [line for line in world.calls if " up -d " in line]


@pytest.mark.parametrize("point", WHILE_APPLYING)
def test_a_crash_while_applying_rolls_back_to_an_identical_vault(
    tmp_path: Path, point: str
) -> None:
    world = World(tmp_path)
    world.release("1.5.2", migrate_to="rev2")
    before = world.live_db
    world.request("v1.5.2")

    world.run(CIPHERMOTH_UPDATER_FAULT=f"kill:{point}")
    _killed(world)
    assert world.maintenance is not None
    world.run()

    _converged(world)
    assert world.journal["phase"] == "rolled_back"
    assert world.result["state"] == "rolled_back"
    assert world.running() == "1.5.1"
    assert world.live_db == before


def test_a_crash_after_committing_finishes_the_update(tmp_path: Path) -> None:
    world = World(tmp_path)
    world.release("1.5.2", migrate_to="rev2")
    world.request("v1.5.2")

    world.run(CIPHERMOTH_UPDATER_FAULT="kill:committed")
    _killed(world)
    assert world.maintenance is not None
    world.run()

    _converged(world)
    assert world.journal["phase"] == "committed"
    assert world.result["state"] == "success"
    assert world.running() == "1.5.2"
    assert world.live_db["alembic"] == "rev2"


@pytest.mark.parametrize("point", ROLLBACK_POINTS)
def test_a_crash_during_rollback_still_restores_the_vault(
    tmp_path: Path, point: str
) -> None:
    world = World(tmp_path)
    world.release("1.5.2", migrate_to="rev2")
    world.flag("backend_health_fail")
    before = world.live_db
    world.request("v1.5.2")

    world.run(CIPHERMOTH_UPDATER_FAULT=f"kill:{point}")
    _killed(world)
    assert world.journal["phase"] == "rolling_back"
    world.run()

    _converged(world)
    assert world.journal["phase"] == "rolled_back"
    assert world.running() == "1.5.1"
    assert world.live_db == before
    restores = [line for line in world.calls if line.startswith("pg_restore -w")]
    expected = 3 if point == "restore_created" else 2
    assert len(restores) == expected


def test_repeated_crashes_during_rollback_converge(tmp_path: Path) -> None:
    world = World(tmp_path)
    world.release("1.5.2", migrate_to="rev2")
    world.flag("backend_health_fail")
    before = world.live_db
    world.request("v1.5.2")

    world.run(CIPHERMOTH_UPDATER_FAULT="kill:env_written")
    _killed(world)
    world.run(CIPHERMOTH_UPDATER_FAULT="kill:restore_created")
    _killed(world)
    world.run(CIPHERMOTH_UPDATER_FAULT="kill:restore_swapped")
    _killed(world)
    world.run(CIPHERMOTH_UPDATER_FAULT="kill:rollback_started")
    _killed(world)
    world.run()

    _converged(world)
    assert world.journal["phase"] == "rolled_back"
    assert world.live_db == before


def test_a_failed_migration_restores_the_identical_vault(tmp_path: Path) -> None:
    world = World(tmp_path)
    world.release("1.5.2", migrate_to="rev2", migration_fails=True)
    before = world.live_db
    world.request("v1.5.2")

    world.run()

    _converged(world)
    assert world.result["state"] == "rolled_back", world.log
    assert "restored from the snapshot" in world.result["detail"]
    assert world.live_db == before
    assert world.running() == "1.5.1"


def test_a_frontend_that_fails_its_check_rolls_back(tmp_path: Path) -> None:
    world = World(tmp_path)
    world.release("1.5.2", migrate_to="rev2")
    world.flag("frontend_config_error_1.5.2")
    before = world.live_db
    world.request("v1.5.2")

    world.run()

    _converged(world)
    assert world.result["state"] == "rolled_back"
    assert "configuration" in world.result["detail"]
    assert world.live_db == before


def test_a_frontend_that_does_not_answer_rolls_back(tmp_path: Path) -> None:
    world = World(tmp_path)
    world.release("1.5.2")
    world.flag("frontend_health_fail")
    world.request("v1.5.2")

    world.run()

    _converged(world)
    assert world.result["state"] == "rolled_back"
    assert world.running("frontend") == "1.5.1"


def test_a_failed_restart_rolls_back(tmp_path: Path) -> None:
    world = World(tmp_path)
    world.release("1.5.2")
    world.flag("up_fail")
    world.request("v1.5.2")

    world.run()

    _converged(world)
    assert world.result["state"] == "rolled_back"


def test_an_unusable_snapshot_stops_the_update(tmp_path: Path) -> None:
    world = World(tmp_path)
    world.release("1.5.2", migrate_to="rev2")
    before = world.live_db
    world.request("v1.5.2")

    world.run(CIPHERMOTH_UPDATER_FAULT="corrupt:snapshot")

    _converged(world)
    assert world.result["state"] == "failed"
    assert "snapshot" in world.result["detail"]
    assert world.running() == "1.5.1"
    assert world.live_db == before
    assert not [n for n in world.snapshots if n.endswith(".dump")]


def test_a_pull_failure_changes_nothing(tmp_path: Path) -> None:
    world = World(tmp_path)
    world.release("1.5.2")
    world.flag("pull_fail")
    world.request("v1.5.2")

    world.run()

    assert world.result["state"] == "failed"
    assert "pull" in world.result["detail"]
    assert not [line for line in world.calls if " stop " in line or "pg_dump" in line]
    assert world.running() == "1.5.1"


def test_an_unverifiable_rollback_target_is_refused(tmp_path: Path) -> None:
    world = World(tmp_path)
    world.release("1.5.2")
    running = world.state["containers"]["backend"]["image"]
    world.state["unsigned"].extend(world.state["images"][running]["digests"])
    world.save()
    world.request("v1.5.2")

    world.run()

    assert world.result["state"] == "failed"
    assert "rollback target" in world.result["detail"]
    assert not [line for line in world.calls if "pg_dump" in line]


def test_a_rollback_target_without_a_registry_digest_is_refused(
    tmp_path: Path,
) -> None:
    world = World(tmp_path)
    world.release("1.5.2")
    running = world.state["containers"]["backend"]["image"]
    world.state["images"][running]["digests"] = []
    world.save()
    world.request("v1.5.2")

    world.run()

    assert world.result["state"] == "failed"
    assert "cannot be verified" in world.result["detail"]


def test_a_release_that_needs_a_newer_updater_is_refused(tmp_path: Path) -> None:
    world = World(tmp_path)
    world.release("1.6.0", migrate_to="rev2", min_protocol="3")
    world.request("v1.6.0")

    world.run()

    assert world.result["state"] == "failed"
    detail = world.result["detail"]
    assert "needs updater protocol 3" in detail
    assert "--profile autoupdate pull updater" in detail
    assert not [line for line in world.calls if " stop " in line]
    assert world.env_version == "1.5.1"


def test_a_compose_file_that_runs_other_images_is_refused(tmp_path: Path) -> None:
    world = World(tmp_path)
    world.release("1.5.2")
    world.state["compose_repo"] = "evil.example/ciphermoth"
    world.save()
    world.request("v1.5.2")

    world.run()

    assert world.result["state"] == "failed"
    assert "Nothing was changed" in world.result["detail"]
    assert not [line for line in world.calls if " stop " in line]


def test_a_mismatched_env_is_refused(tmp_path: Path) -> None:
    world = World(tmp_path)
    world.release("1.5.2")
    world.env_file.write_text(
        world.env_file.read_text().replace("VERSION=1.5.1", "VERSION=1.5.2")
    )
    world.request("v1.5.3")

    world.run()

    assert world.result["state"] == "failed"
    assert "names version 1.5.2 but 1.5.1 is running" in world.result["detail"]


def test_a_baseline_that_is_already_broken_is_refused(tmp_path: Path) -> None:
    world = World(tmp_path)
    world.release("1.5.2")
    world.flag("frontend_config_error_1.5.1")
    world.request("v1.5.2")

    world.run()

    assert world.result["state"] == "failed"
    assert "not fully healthy before the update" in world.result["detail"]
    assert not [line for line in world.calls if line.startswith("docker pull")]


def test_latest_is_restored_on_rollback(tmp_path: Path) -> None:
    world = World(tmp_path)
    world.env_file.write_text(
        world.env_file.read_text().replace("VERSION=1.5.1", "VERSION=latest")
    )
    world.load()
    world.state["tags"]["ghcr.io/mr-grj/ciphermoth-backend:latest"] = world.state[
        "containers"
    ]["backend"]["image"]
    world.state["tags"]["ghcr.io/mr-grj/ciphermoth-frontend:latest"] = world.state[
        "containers"
    ]["frontend"]["image"]
    for service in ("backend", "frontend"):
        world.state["containers"][service]["ref"] = (
            f"ghcr.io/mr-grj/ciphermoth-{service}:latest"
        )
    world.save()
    original = world.env_file.read_bytes()
    world.release("1.5.2")
    world.flag("backend_health_fail")
    world.request("v1.5.2")

    world.run()

    assert world.result["state"] == "rolled_back", world.log
    assert world.env_file.read_bytes() == original
    assert world.running() == "1.5.1"


def test_a_removed_previous_image_is_pulled_back_by_digest(tmp_path: Path) -> None:
    world = World(tmp_path)
    world.release("1.5.2")
    world.flag("backend_health_fail")
    world.request("v1.5.2")
    world.run(CIPHERMOTH_UPDATER_FAULT="kill:compose_up_done")
    _killed(world)
    world.load()
    removed = world.state["tags"].pop("ghcr.io/mr-grj/ciphermoth-backend:1.5.1")
    world.state["absent"] = [removed]
    world.save()

    world.run()

    _converged(world)
    assert world.running() == "1.5.1"
    pulls = [line for line in world.calls if line.startswith("docker pull")]
    assert pulls[-1].startswith("docker pull ghcr.io/mr-grj/ciphermoth-backend@sha256:")


def test_a_restore_that_keeps_failing_needs_intervention(tmp_path: Path) -> None:
    world = World(tmp_path)
    world.release("1.5.2", migrate_to="rev2")
    world.flag("backend_health_fail", "restore_fail")
    before = world.live_db
    world.request("v1.5.2")

    world.run()

    assert world.journal["phase"] == "intervention", world.log
    assert world.result["state"] == "intervention"
    assert "Manual recovery" in world.result["detail"]
    assert world.maintenance is not None
    snapshot = world.journal["snapshot"]["name"]
    assert f"{snapshot}.dump" in world.snapshots
    assert world.live_db["alembic"] == "rev2"

    world.request("v1.5.3")
    world.run()
    assert "needs manual attention" in world.result["detail"]
    assert world.journal["phase"] == "intervention"

    world.unflag("restore_fail")
    assert world.run("resolve").returncode == 0
    assert world.journal["phase"] == "resolved"
    assert world.maintenance is None
    assert world.live_db != before


def test_an_unreadable_journal_pauses_updates(tmp_path: Path) -> None:
    world = World(tmp_path)
    world.release("1.5.2")
    state = world.backups / "state"
    state.mkdir(parents=True)
    (state / "journal.json").write_text("{not json")
    world.request("v1.5.2")

    world.run()

    assert world.result["state"] == "failed"
    assert "journal is unreadable" in world.result["detail"]
    assert world.running() == "1.5.1"
    assert not [line for line in world.calls if line.startswith("docker pull")]


def test_a_replayed_request_is_refused(tmp_path: Path) -> None:
    world = World(tmp_path)
    world.release("1.5.2")
    world.flag("backend_health_fail")
    request = world.request("v1.5.2")
    world.run()
    assert world.result["state"] == "rolled_back"
    world.unflag("backend_health_fail")

    (world.control / "request.json").write_text(json.dumps(request))
    world.run()

    assert world.result["state"] == "failed"
    assert "already handled" in world.result["detail"]
    assert world.running() == "1.5.1"


@pytest.mark.parametrize("kind", ["symlink", "fifo", "huge", "array"])
def test_hostile_request_files_are_refused(tmp_path: Path, kind: str) -> None:
    world = World(tmp_path)
    world.release("1.5.2")
    secret = tmp_path / "secret"
    secret.write_text('{"target": "v1.5.2"}')
    request = world.control / "request.json"
    if kind == "symlink":
        request.symlink_to(secret)
    elif kind == "fifo":
        os.mkfifo(request)
    elif kind == "huge":
        request.write_text(json.dumps({"target": "v1.5.2", "pad": "x" * 10000}))
    else:
        request.write_text('["v1.5.2"]')

    world.run()

    assert world.result["state"] == "failed"
    assert not os.path.lexists(request)
    assert secret.exists()
    assert world.running() == "1.5.1"


def test_concurrent_updaters_apply_one_update_once(tmp_path: Path) -> None:
    world = World(tmp_path)
    world.release("1.5.2")
    world.request("v1.5.2")
    results: list[subprocess.CompletedProcess[str]] = []

    def run() -> None:
        results.append(
            subprocess.run(
                [sys.executable, str(UPDATER), "once"],
                capture_output=True,
                text=True,
                timeout=120,
                env=world.environment(),
            )
        )

    threads = [threading.Thread(target=run) for _ in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    world.load()

    assert all(result.returncode == 0 for result in results)
    assert len([line for line in world.calls if line.startswith("pg_dump")]) == 1
    assert world.result["state"] == "success"
    assert world.running() == "1.5.2"


def test_a_second_request_after_an_update_is_judged_against_the_new_version(
    tmp_path: Path,
) -> None:
    world = World(tmp_path)
    world.release("1.5.2")
    world.request("v1.5.2")
    world.run()
    assert world.running() == "1.5.2"

    world.request("v1.5.2")
    world.run()

    assert world.result["state"] == "failed"
    assert "not newer than the running version 1.5.2" in world.result["detail"]


def test_writes_made_before_the_boundary_survive_a_rollback(tmp_path: Path) -> None:
    world = World(tmp_path)
    world.release("1.5.2", migrate_to="rev2", migration_fails=True)
    world.write_data([3, "created just before the update", "gAAAAAnew", None])
    expected = world.live_db
    world.request("v1.5.2")

    world.run()

    assert world.result["state"] == "rolled_back"
    assert world.live_db == expected
    names = [row[1] for row in world.live_db["tables"]["public.passwords"]]
    assert "created just before the update" in names


def test_recovery_waits_for_docker_after_a_reboot(tmp_path: Path) -> None:
    world = World(tmp_path)
    world.release("1.5.2", migrate_to="rev2")
    before = world.live_db
    world.request("v1.5.2")
    world.run(CIPHERMOTH_UPDATER_FAULT="kill:compose_up_done")
    _killed(world)
    world.load()
    world.state["docker_down"] = 3
    world.save()

    world.run(DEPENDENCY_TIMEOUT="30", RETRY_INTERVAL="0.05")

    _converged(world)
    assert world.live_db == before
    assert "waiting for Docker and the database" in world.log


def test_a_recreated_updater_of_another_version_finishes_the_recovery(
    tmp_path: Path,
) -> None:
    world = World(tmp_path)
    world.release("1.5.2", migrate_to="rev2")
    before = world.live_db
    world.request("v1.5.2")
    world.run(CIPHERMOTH_UPDATER_FAULT="kill:compose_up_done")
    _killed(world)

    world.run(CIPHERMOTH_UPDATER_VERSION="1.5.2")

    _converged(world)
    assert world.journal["phase"] == "rolled_back"
    assert world.live_db == before


def test_an_update_interrupted_under_the_previous_updater_is_reported(
    tmp_path: Path,
) -> None:
    world = World(tmp_path)
    world.env_file.write_text(
        world.env_file.read_text().replace("VERSION=1.5.1", "VERSION=1.5.2")
    )
    (world.control / "result.json").write_text(
        json.dumps(
            {
                "state": "applying",
                "detail": "Applying update and restarting",
                "target": "v1.5.2",
                "finished_at": "2026-10-12T10:00:00Z",
            }
        )
    )

    world.run()

    assert world.result["state"] == "failed"
    assert "interrupted" in world.result["detail"]
    assert world.env_version == "1.5.1"
    assert "OTHER=kept" in world.env_file.read_text()


def test_stray_temporary_databases_are_dropped(tmp_path: Path) -> None:
    world = World(tmp_path)
    world.state["databases"]["ciphermoth_verify_0123456789ab"] = initial_database("x")
    world.state["databases"]["ciphermoth_failed_0123456789ab"] = initial_database("x")
    world.state["databases"]["other_restore_0123456789ab"] = initial_database("x")
    world.save()

    world.run()

    assert world.database_names == [
        "ciphermoth",
        "ciphermoth_failed_0123456789ab",
        "other_restore_0123456789ab",
    ]


def test_snapshots_are_kept_within_the_retention_limit(tmp_path: Path) -> None:
    world = World(tmp_path)
    for minor in range(2, 7):
        world.release(f"1.5.{minor}")
        world.request(f"v1.5.{minor}")
        world.run(SNAPSHOT_KEEP="2")
        assert world.result["state"] == "success", world.log

    dumps = [n for n in world.snapshots if n.endswith(".dump")]
    assert len(dumps) == 2
    assert len([n for n in world.snapshots if n.endswith(".json")]) == 2
    mode = (world.backups / "snapshots" / dumps[0]).stat().st_mode & 0o777
    assert mode == 0o600
    assert (world.backups / "snapshots").stat().st_mode & 0o777 == 0o700


def test_the_database_password_never_leaves_the_pgpass_file(tmp_path: Path) -> None:
    world = World(tmp_path)
    world.release("1.5.2", migrate_to="rev2", migration_fails=True)
    world.request("v1.5.2")

    world.run()

    assert world.result["state"] == "rolled_back"
    assert world.secrets_leaked() == []
    assert (tmp_path / "pgpass").stat().st_mode & 0o777 == 0o600


def test_the_heartbeat_reports_the_protocol_and_a_stopped_updater(
    tmp_path: Path,
) -> None:
    world = World(tmp_path)

    world.serve_for(2)

    heartbeat = json.loads((world.control / "updater.json").read_text())
    assert heartbeat["protocol"] == 2
    assert heartbeat["running"] is False
    assert (world.control / "updater.ready").exists()
