import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
INSTALLER = ROOT / "install.sh"

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX shell")

DOCKER = """#!/bin/sh
echo "docker $*" >> "$STUB_LOG"
if [ "$1 $2" = "volume inspect" ]; then
  [ "$3" = "ciphermoth_postgres_data" ] && [ -n "$STUB_POSTGRES_VOLUME" ] && exit 0
  exit 1
fi
exit 0
"""

CURL = """#!/bin/sh
echo "curl $*" >> "$STUB_LOG"
url=""
out=""
while [ $# -gt 0 ]; do
  case "$1" in
    -o) out="$2"; shift 2 ;;
    -*) shift ;;
    *) url="$1"; shift ;;
  esac
done
cp "$STUB_REPO/${url#*/master/}" "$out"
"""

LEGACY_COMPOSE = """name: ciphermoth
services:
  db:
    image: postgres:16-alpine
"""


def _stubs(tmp_path: Path) -> dict[str, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (("docker", DOCKER), ("curl", CURL)):
        (bin_dir / name).write_text(body)
        (bin_dir / name).chmod(0o755)
    return {
        "PATH": f"{bin_dir}:/usr/bin:/bin",
        "HOME": str(tmp_path),
        "STUB_LOG": str(tmp_path / "calls.log"),
        "STUB_REPO": str(ROOT),
    }


def _install(tmp_path: Path, folder: Path, **env: str) -> subprocess.CompletedProcess:
    environment = {**_stubs_once(tmp_path), "CIPHERMOTH_DIR": str(folder), **env}
    return subprocess.run(
        ["sh", str(INSTALLER)],
        env=environment,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=60,
        start_new_session=True,
    )


_PREPARED: dict[Path, dict[str, str]] = {}


def _stubs_once(tmp_path: Path) -> dict[str, str]:
    if tmp_path not in _PREPARED:
        _PREPARED[tmp_path] = _stubs(tmp_path)
    return _PREPARED[tmp_path]


def _calls(tmp_path: Path) -> list[str]:
    log = tmp_path / "calls.log"
    return log.read_text().splitlines() if log.exists() else []


def _assert_never_removes_anything(tmp_path: Path) -> None:
    for call in _calls(tmp_path):
        assert " down" not in call, call
        assert "volume rm" not in call, call
        assert " rm " not in call, call
        assert "prune" not in call, call


def _backups(folder: Path, name: str) -> list[Path]:
    return sorted(folder.glob(f"{name}.backup-*"))


def test_a_fresh_install_writes_the_release_files_and_starts_the_stack(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "ciphermoth"
    result = _install(tmp_path, folder)

    assert result.returncode == 0, result.stderr
    assert (folder / "docker-compose.prod.yml").read_bytes() == (
        ROOT / "docker-compose.prod.yml"
    ).read_bytes()
    assert os.access(folder / "cip", os.X_OK)
    assert "CIPHERMOTH_VERSION=latest" in (folder / ".env").read_text()
    calls = _calls(tmp_path)
    assert "docker compose -f docker-compose.prod.yml pull" in calls
    assert "docker compose -f docker-compose.prod.yml up -d --remove-orphans" in calls
    assert "signed images" not in result.stdout
    _assert_never_removes_anything(tmp_path)


def test_rerunning_on_a_2x_install_keeps_its_settings_and_backups(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "ciphermoth"
    assert _install(tmp_path, folder).returncode == 0
    env = "CIPHERMOTH_VERSION=2.0.0\nCIPHERMOTH_BIND_ADDRESS=0.0.0.0\n"
    (folder / ".env").write_text(env)
    (folder / "docker-compose.prod.yml.backup-20260101T000000Z").write_text("old")

    result = _install(tmp_path, folder)

    assert result.returncode == 0, result.stderr
    assert (folder / ".env").read_text() == env
    assert _backups(folder, ".env") == []
    assert [p.name for p in _backups(folder, "docker-compose.prod.yml")] == [
        "docker-compose.prod.yml.backup-20260101T000000Z"
    ]
    _assert_never_removes_anything(tmp_path)


def test_a_changed_compose_file_is_backed_up_without_overwriting_older_backups(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "ciphermoth"
    folder.mkdir()
    for content in ("first local edit", "second local edit"):
        (folder / "docker-compose.prod.yml").write_text(content)
        assert _install(tmp_path, folder).returncode == 0

    kept = sorted(p.read_text() for p in _backups(folder, "docker-compose.prod.yml"))
    assert kept == ["first local edit", "second local edit"]


def test_a_1x_version_pin_is_reset_and_the_old_env_kept(tmp_path: Path) -> None:
    folder = tmp_path / "ciphermoth"
    folder.mkdir()
    old = (
        "POSTGRES_PASSWORD=secret\nCIPHERMOTH_VERSION=1.6.0\n"
        "CIPHERMOTH_BACKEND_PORT=9000\n"
    )
    (folder / ".env").write_text(old)

    result = _install(tmp_path, folder)

    assert result.returncode == 0, result.stderr
    assert (folder / ".env").read_text() == (
        "POSTGRES_PASSWORD=secret\nCIPHERMOTH_VERSION=latest\n"
        "CIPHERMOTH_BACKEND_PORT=9000\n"
    )
    [kept] = _backups(folder, ".env")
    assert kept.read_text() == old


@pytest.mark.parametrize("found_by", ["volume", "compose file"])
def test_a_postgresql_install_is_left_alone_without_confirmation(
    tmp_path: Path, found_by: str
) -> None:
    folder = tmp_path / "ciphermoth"
    env: dict[str, str] = {}
    if found_by == "volume":
        env["STUB_POSTGRES_VOLUME"] = "1"
    else:
        folder.mkdir()
        (folder / "docker-compose.prod.yml").write_text(LEGACY_COMPOSE)
        (folder / ".env").write_text("CIPHERMOTH_VERSION=1.6.0\n")

    result = _install(tmp_path, folder, **env)

    assert result.returncode != 0
    assert "Nothing was changed" in result.stdout + result.stderr
    if found_by == "volume":
        assert not folder.exists()
    else:
        assert (folder / "docker-compose.prod.yml").read_text() == LEGACY_COMPOSE
        assert (folder / ".env").read_text() == "CIPHERMOTH_VERSION=1.6.0\n"
        assert sorted(p.name for p in folder.iterdir()) == [
            ".env",
            "docker-compose.prod.yml",
        ]
    calls = _calls(tmp_path)
    assert not any(call.startswith("curl") for call in calls), calls
    assert not any(" pull" in call or " up " in call for call in calls), calls


def test_a_confirmed_postgresql_install_keeps_its_files_and_volumes(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "ciphermoth"
    folder.mkdir()
    (folder / "docker-compose.prod.yml").write_text(LEGACY_COMPOSE)
    (folder / ".env").write_text("POSTGRES_PASSWORD=secret\nCIPHERMOTH_VERSION=1.6.0\n")

    result = _install(tmp_path, folder, STUB_POSTGRES_VOLUME="1", CIPHERMOTH_FRESH="y")

    assert result.returncode == 0, result.stderr
    [compose] = _backups(folder, "docker-compose.prod.yml")
    assert compose.read_text() == LEGACY_COMPOSE
    [env] = _backups(folder, ".env")
    assert "CIPHERMOTH_VERSION=1.6.0" in env.read_text()
    assert "CIPHERMOTH_VERSION=latest" in (folder / ".env").read_text()
    _assert_never_removes_anything(tmp_path)
