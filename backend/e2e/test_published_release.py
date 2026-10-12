import os
from collections.abc import Callable, Iterator

import pytest

from e2e.stack import Stack, golden, sh
from tests.integrity import assert_same_vault

RELEASE = os.environ.get("E2E_PUBLISHED_RELEASE", "")
PREVIOUS = os.environ.get("E2E_PREVIOUS_RELEASE", "1.5.0")
GOLDEN = golden()
MASTER = GOLDEN["master_password"]
KEY = GOLDEN["key"]
BASE_HEAD = "9c0d1e2f3a4b"
GHCR = "ghcr.io/mr-grj"

pytestmark = pytest.mark.skipif(
    not RELEASE, reason="set E2E_PUBLISHED_RELEASE to smoke-test published images"
)


@pytest.fixture
def stacks() -> Iterator[Callable[..., Stack]]:
    created: list[Stack] = []
    for service in ("backend", "frontend", "updater"):
        for version in (PREVIOUS, RELEASE):
            sh("docker", "pull", "-q", f"{GHCR}/ciphermoth-{service}:{version}")

    def make(name: str, **kwargs) -> Stack:
        stack = Stack(f"published-{name}", PREVIOUS, registry=None, **kwargs)
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


def _no_stub(stack: Stack) -> None:
    labels = stack.container("updater")["Config"]["Labels"] or {}
    assert "io.ciphermoth.e2e" not in labels


def test_the_previous_updater_installs_the_release_then_hands_over(stacks) -> None:
    stack = stacks("bootstrap")
    _no_stub(stack)
    token = stack.unlock(MASTER)
    before = stack.vault(KEY, MASTER)

    resp = stack.apply(token, f"v{RELEASE}")
    assert resp.status_code == 200, resp.text
    stack.wait_for(lambda: stack.meta() == RELEASE, 600, "the release backend")
    status = stack.wait_result()

    assert status["state"] == "success", status
    assert status["updater_upgrade_required"] is True
    assert stack.frontend_version() == RELEASE
    assert stack.revision() == BASE_HEAD
    _identical(stack, before)
    token = stack.unlock(MASTER)
    refused = stack.apply(token, "v99.0.0")
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
    _no_stub(stack)
    status = stack.status() or {}
    assert status["updater_present"] is True
    assert status["updater_version"] == RELEASE
    assert stack.apply(token, f"v{RELEASE}").status_code == 403
    _identical(stack, before)


def _v2_stack(stacks, name: str, fault: str = "") -> Stack:
    return stacks(
        name,
        updater_image=f"{GHCR}/ciphermoth-updater:{RELEASE}",
        fault=fault,
    )


def test_updater_v2_installs_a_signed_release(stacks) -> None:
    stack = _v2_stack(stacks, "v2-update")
    _no_stub(stack)
    token = stack.unlock(MASTER)
    before = stack.vault(KEY, MASTER)

    assert stack.apply(token, f"v{RELEASE}").status_code == 200
    status = stack.wait_result()

    assert status["state"] == "success", status
    assert stack.meta() == RELEASE
    assert stack.frontend_version() == RELEASE
    assert stack.env_version() == RELEASE
    assert stack.revision() == BASE_HEAD
    assert not status["maintenance"]
    _identical(stack, before)
    logs = stack.logs("updater")
    assert logs.count("signature verified") >= 4
    assert "COSIGN STUBBED" not in logs
    assert any(f.endswith(".dump") for f in stack.backups())


def test_updater_v2_rolls_back_a_signed_release(stacks) -> None:
    stack = _v2_stack(stacks, "v2-rollback", "fail:validated,kill:restore_created")
    token = stack.unlock(MASTER)
    assert stack.add_entry(token, "written just before").status_code == 200
    before = stack.vault(KEY, MASTER)

    assert stack.apply(token, f"v{RELEASE}").status_code == 200
    status = stack.wait_result()

    assert status["state"] == "rolled_back", status
    assert stack.container("updater")["RestartCount"] >= 1
    assert stack.meta() == PREVIOUS
    assert stack.env_version() == PREVIOUS
    assert stack.revision() == BASE_HEAD
    _identical(stack, before)
    assert "COSIGN STUBBED" not in stack.logs("updater")
