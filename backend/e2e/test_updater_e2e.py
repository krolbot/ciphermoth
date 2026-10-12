import json
import subprocess
import time
from collections.abc import Callable, Iterator

import pytest

from e2e.stack import (
    CANDIDATE,
    PUBLISHED,
    Stack,
    build_images,
    golden,
    sh,
)
from tests.integrity import assert_same_vault, diff_ciphertext

GOLDEN = golden()
MASTER = GOLDEN["master_password"]
KEY = GOLDEN["key"]
BASE_HEAD = "9c0d1e2f3a4b"
GOOD_HEAD = "e2e000000001"


@pytest.fixture(scope="session")
def images() -> dict[str, str]:
    return build_images()


@pytest.fixture
def stacks(images: dict[str, str]) -> Iterator[Callable[..., Stack]]:
    created: list[Stack] = []

    def make(name: str, *args, **kwargs) -> Stack:
        stack = Stack(name, *args, **kwargs)
        created.append(stack)
        stack.start()
        return stack

    yield make
    for stack in created:
        stack.down()


def _identical(stack: Stack, before: tuple) -> None:
    raw_before, contents_before = before
    raw_after, contents_after = stack.vault(KEY, MASTER)
    assert raw_after == raw_before
    assert_same_vault(contents_before, contents_after)
    assert contents_after.settings == contents_before.settings


def _healthy_on(stack: Stack, version: str) -> None:
    assert stack.meta() == version
    assert stack.api.get("/health").json()["schema"] == "current"
    assert stack.frontend_version() == version
    assert "CipherMoth cannot start" not in stack.frontend_page()
    assert stack.env_version() == version
    assert not (stack.status() or {}).get("maintenance")


def _apply(stack: Stack, token: str, target: str) -> str:
    resp = stack.apply(token, target)
    assert resp.status_code == 200, resp.text
    return resp.json()["request_id"]


def test_bootstrap_from_the_published_release(stacks) -> None:
    stack = stacks("bootstrap", PUBLISHED)
    token = stack.unlock(MASTER)
    assert stack.add_entry(token, "before the bootstrap").status_code == 200
    before = stack.vault(KEY, MASTER)

    resp = stack.apply(token, f"v{CANDIDATE}")
    assert resp.status_code == 200, resp.text
    stack.wait_for(lambda: stack.meta() == CANDIDATE, 600, "the candidate backend")
    status = stack.wait_result()

    assert status["state"] == "success", status
    assert status["updater_protocol"] == 1
    assert status["updater_upgrade_required"] is True
    assert stack.frontend_version() == CANDIDATE
    _identical(stack, before)
    token = stack.unlock(MASTER)
    refused = stack.apply(token, "v1.5.2")
    assert refused.status_code == 403
    assert "--profile autoupdate pull updater" in refused.json()["detail"]

    sh(
        "sh",
        "-c",
        "docker compose -f docker-compose.prod.yml --profile autoupdate pull updater"
        " && docker compose -f docker-compose.prod.yml --profile autoupdate up -d"
        " --no-deps updater",
        cwd=stack.dir,
    )
    stack.wait_for(
        lambda: (stack.status() or {}).get("updater_protocol") == 2,
        120,
        "the new updater",
    )
    assert stack.status()["updater_present"] is True

    request_id = _apply(stack, token, "v1.5.2")
    status = stack.wait_result(request_id)

    assert status["state"] == "success", status
    _healthy_on(stack, "1.5.2")
    _identical(stack, before)
    snapshots = [f for f in stack.backups() if f.startswith("/b/snapshots/")]
    assert len([f for f in snapshots if f.endswith(".dump")]) == 1
    assert any(f.endswith(".sql") for f in stack.backups())


def test_an_update_with_a_schema_migration_succeeds(stacks) -> None:
    stack = stacks("migrate")
    token = stack.unlock(MASTER)
    raw_before, contents_before = stack.vault(KEY, MASTER)

    status = stack.wait_result(_apply(stack, token, "v1.5.3"))

    assert status["state"] == "success", status
    _healthy_on(stack, "1.5.3")
    assert stack.revision() == GOOD_HEAD
    assert stack.query("SELECT note FROM e2e_audit") == [("migrated",)]
    raw_after, contents_after = stack.vault(KEY, MASTER)
    assert_same_vault(contents_before, contents_after)
    assert diff_ciphertext(raw_before, raw_after) == []
    token = stack.unlock(MASTER)
    assert len(stack.entry_names(token)) == len(
        [e for e in contents_before.entries if not e.trashed]
    )


def test_a_failed_migration_restores_an_identical_vault(stacks) -> None:
    stack = stacks("failing-migration")
    token = stack.unlock(MASTER)
    assert stack.add_entry(token, "written just before").status_code == 200
    before = stack.vault(KEY, MASTER)
    tables = stack.tables()

    status = stack.wait_result(_apply(stack, token, "v1.5.4"))

    assert status["state"] == "rolled_back", status
    assert "restored from the snapshot" in status["detail"]
    _healthy_on(stack, CANDIDATE)
    assert stack.revision() == BASE_HEAD
    assert stack.tables() == tables
    _identical(stack, before)
    token = stack.unlock(MASTER)
    assert "written just before" in stack.entry_names(token)


def test_a_broken_frontend_rolls_back_a_completed_migration(stacks) -> None:
    stack = stacks("broken-frontend")
    token = stack.unlock(MASTER)
    before = stack.vault(KEY, MASTER)
    tables = stack.tables()
    settings = stack.settings_rows()

    status = stack.wait_result(_apply(stack, token, "v1.5.5"))

    assert status["state"] == "rolled_back", status
    assert "web UI" in status["detail"]
    _healthy_on(stack, CANDIDATE)
    assert stack.revision() == BASE_HEAD
    assert stack.tables() == tables
    assert stack.settings_rows() == settings
    _identical(stack, before)


def test_a_killed_updater_recovers_on_restart(stacks) -> None:
    stack = stacks("killed", fault="kill:compose_up_done")
    token = stack.unlock(MASTER)
    before = stack.vault(KEY, MASTER)

    status = stack.wait_result(_apply(stack, token, "v1.5.3"))

    assert status["state"] == "rolled_back", status
    assert "interrupted" in status["detail"]
    assert stack.container("updater")["RestartCount"] >= 1
    _healthy_on(stack, CANDIDATE)
    assert stack.revision() == BASE_HEAD
    _identical(stack, before)


def test_writes_are_refused_while_the_updater_is_down_mid_update(stacks) -> None:
    stack = stacks("reboot", fault="kill:validated", updater_restart="no")
    token = stack.unlock(MASTER)
    before = stack.vault(KEY, MASTER)

    _apply(stack, token, "v1.5.3")
    stack.wait_for(
        lambda: stack.container("updater")["State"]["Status"] == "exited",
        600,
        "the updater to die",
    )
    assert stack.meta() == "1.5.3"
    assert stack.revision() == GOOD_HEAD
    assert stack.status()["maintenance"] is True
    blocked = stack.api.post(
        "/master_password/unlock", json={"master_password": MASTER}
    )
    assert blocked.status_code == 503
    assert blocked.json()["code"] == "maintenance"

    stack.compose("up", "-d")
    status = stack.wait_result()

    assert status["state"] == "rolled_back", status
    _healthy_on(stack, CANDIDATE)
    assert stack.revision() == BASE_HEAD
    _identical(stack, before)


def test_an_old_updater_cannot_migrate_the_database(stacks) -> None:
    stack = stacks(
        "old-updater-migration",
        PUBLISHED,
        extra_env={"E2E_HEALTH_RETRIES": "20", "E2E_HEALTH_INTERVAL": "3"},
    )
    token = stack.unlock(MASTER)
    before = stack.vault(KEY, MASTER)
    tables = stack.tables()
    refusals: list[str] = []

    resp = stack.apply(token, "v1.5.3")
    assert resp.status_code == 200, resp.text
    deadline = time.monotonic() + 900
    status: dict = {}
    while time.monotonic() < deadline:
        logs = stack.logs("backend")
        if "will not change the database schema" in logs:
            refusals.append(logs)
        status = stack.status() or {}
        if status.get("state") in ("success", "failed", "rolled_back"):
            break
        time.sleep(2)

    assert status.get("state") == "rolled_back", status
    assert refusals, "the 1.5.3 backend never refused to migrate"
    assert stack.meta() == PUBLISHED
    assert stack.revision() == BASE_HEAD
    assert stack.tables() == tables
    _identical(stack, before)


def test_an_unreachable_database_stops_the_update_before_any_change(stacks) -> None:
    stack = stacks("no-db", extra_env={"E2E_UPDATER_DB_HOST": "nowhere"})
    token = stack.unlock(MASTER)
    before = stack.vault(KEY, MASTER)

    status = stack.wait_result(_apply(stack, token, "v1.5.2"))

    assert status["state"] == "failed", status
    assert "Nothing was changed" in status["detail"]
    _healthy_on(stack, CANDIDATE)
    _identical(stack, before)
    assert not [f for f in stack.backups() if f.endswith(".dump")]


def test_real_cosign_refuses_unsigned_images(stacks, images) -> None:
    stack = stacks("real-cosign", updater_image=images["updater:real"])
    token = stack.unlock(MASTER)
    before = stack.vault(KEY, MASTER)

    status = stack.wait_result(_apply(stack, token, "v1.5.2"))

    assert status["state"] == "failed", status
    assert "signature" in status["detail"]
    assert "Nothing was changed" in status["detail"]
    _healthy_on(stack, CANDIDATE)
    _identical(stack, before)


def _verify(image: str, ref: str, *env: str) -> subprocess.CompletedProcess[str]:
    args = ["docker", "run", "--rm", "--entrypoint", "python3"]
    for item in env:
        args += ["-e", item]
    return sh(
        *args,
        image,
        "/usr/local/lib/ciphermoth/updater.py",
        "verify-image",
        ref,
        check=False,
        timeout=300,
    )


def test_real_cosign_accepts_the_official_signature_only(images) -> None:
    image = images["updater:real"]
    index = sh(
        "docker",
        "buildx",
        "imagetools",
        "inspect",
        f"ghcr.io/mr-grj/ciphermoth-backend:{PUBLISHED}",
        "--format",
        "{{json .Manifest}}",
    ).stdout
    manifest = json.loads(index)
    signed = f"ghcr.io/mr-grj/ciphermoth-backend@{manifest['digest']}"
    platform = next(
        m["digest"]
        for m in manifest["manifests"]
        if m.get("platform", {}).get("architecture") in ("amd64", "arm64")
    )

    official = _verify(image, signed)
    unsigned_platform = _verify(image, f"ghcr.io/mr-grj/ciphermoth-backend@{platform}")
    other_identity = _verify(
        image,
        signed,
        "COSIGN_IDENTITY_REGEXP=^https://github.com/someone-else/ciphermoth/.*",
    )

    assert official.returncode == 0, official.stderr
    assert "signature verified" in official.stderr
    assert unsigned_platform.returncode != 0
    assert other_identity.returncode != 0
