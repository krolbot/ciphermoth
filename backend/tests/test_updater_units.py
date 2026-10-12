import hashlib
import importlib.util
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from tests.updater_harness import UPDATER

_spec = importlib.util.spec_from_file_location("ciphermoth_updater", UPDATER)
assert _spec is not None and _spec.loader is not None
updater = importlib.util.module_from_spec(_spec)
sys.modules["ciphermoth_updater"] = updater
_spec.loader.exec_module(updater)


@pytest.mark.parametrize(
    ("before", "after"),
    [
        (
            b"A=1\nCIPHERMOTH_VERSION=1.5.1\nB=2\n",
            b"A=1\nCIPHERMOTH_VERSION=1.5.2\nB=2\n",
        ),
        (
            b"CIPHERMOTH_VERSION=latest\r\nB=2\r\n",
            b"CIPHERMOTH_VERSION=1.5.2\r\nB=2\r\n",
        ),
        (b"A=1", b"A=1\nCIPHERMOTH_VERSION=1.5.2\n"),
        (b"", b"CIPHERMOTH_VERSION=1.5.2\n"),
        (
            b"CIPHERMOTH_VERSION=1.5.0\n# x\nCIPHERMOTH_VERSION=1.5.1\n",
            b"CIPHERMOTH_VERSION=1.5.2\n# x\nCIPHERMOTH_VERSION=1.5.2\n",
        ),
        (
            b"MY_CIPHERMOTH_VERSION=9\n",
            b"MY_CIPHERMOTH_VERSION=9\nCIPHERMOTH_VERSION=1.5.2\n",
        ),
    ],
)
def test_the_env_version_is_rewritten_in_place(before: bytes, after: bytes) -> None:
    assert updater.with_version(before, "1.5.2") == after


@pytest.mark.parametrize(
    "tag", ["v1.5.2", "latest", "1.5", "1.5.2\nEVIL=1", r"1.5.2\1"]
)
def test_only_plain_versions_are_written_to_env(tag: str) -> None:
    with pytest.raises(ValueError):
        updater.with_version(b"CIPHERMOTH_VERSION=1.5.1\n", tag)


@pytest.mark.parametrize(
    ("text", "version"),
    [
        (b"CIPHERMOTH_VERSION=1.5.1\n", "1.5.1"),
        (b'CIPHERMOTH_VERSION="1.5.1"\n', "1.5.1"),
        (b"CIPHERMOTH_VERSION='latest'\n", "latest"),
        (b"CIPHERMOTH_VERSION=1.5.0\nCIPHERMOTH_VERSION=1.5.1\n", "1.5.1"),
        (b"OTHER=1\n", None),
    ],
)
def test_the_env_version_is_read_like_compose(text: bytes, version: str | None) -> None:
    assert updater.env_version(text) == version


def _request(**fields: object) -> bytes:
    return json.dumps({"target": "v1.5.2", **fields}).encode()


def test_requests_from_older_backends_are_accepted() -> None:
    request = updater.parse_request(_request(), 900)
    assert len(request.id) == 32
    assert request.requested_at is None


@pytest.mark.parametrize(
    ("fields", "reason"),
    [
        (
            {"requested_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat()},
            "future",
        ),
        (
            {"requested_at": (datetime.now(UTC) - timedelta(hours=1)).isoformat()},
            "expired",
        ),
        ({"requested_at": 5}, "invalid time"),
        ({"id": "A" * 32}, "invalid id"),
        ({"id": 7}, "invalid id"),
        ({"target": ["v1.5.2"]}, "release tag"),
    ],
)
def test_requests_are_validated(fields: dict, reason: str) -> None:
    with pytest.raises(updater.Refused, match=reason):
        updater.parse_request(_request(**fields), 900)


def test_a_naive_request_time_is_read_as_utc() -> None:
    naive = datetime.now(UTC).replace(tzinfo=None).isoformat()
    assert updater.parse_request(_request(requested_at=naive), 900).requested_at


def test_the_passfile_escapes_separators(tmp_path: Path) -> None:
    settings = updater.Settings.from_env()
    settings = type(settings)(
        **{**settings.__dict__, "pg_password": r"a:b\c", "pg_user": "u:1"}
    )
    postgres = updater.Postgres(settings, updater.Runner(), tmp_path / "pgpass")

    postgres.write_passfile()

    assert (tmp_path / "pgpass").read_text() == "*:*:*:u\\:1:a\\:b\\\\c\n"
    assert (tmp_path / "pgpass").stat().st_mode & 0o777 == 0o600
    assert "PGPASSWORD" not in postgres.env
    assert "POSTGRES_PASSWORD" not in postgres.env


def _snapshot(directory: Path, name: str, content: bytes = b"dump") -> None:
    (directory / f"{name}.dump").write_bytes(content)
    (directory / f"{name}.json").write_text(
        json.dumps(
            {
                "format": updater.SNAPSHOT_FORMAT,
                "name": name,
                "sha256": hashlib.sha256(content).hexdigest(),
                "size": len(content),
            }
        )
    )


def test_a_snapshot_is_trusted_only_when_it_matches_its_manifest(
    tmp_path: Path,
) -> None:
    snapshots = updater.Snapshots(tmp_path)
    _snapshot(tmp_path, "good")
    _snapshot(tmp_path, "tampered")
    (tmp_path / "tampered.dump").write_bytes(b"dumq")
    _snapshot(tmp_path, "truncated")
    (tmp_path / "truncated.dump").write_bytes(b"du")
    _snapshot(tmp_path, "orphan")
    (tmp_path / "orphan.dump").unlink()

    assert snapshots.verified("good") is not None
    assert snapshots.verified("tampered") is None
    assert snapshots.verified("truncated") is None
    assert snapshots.verified("orphan") is None


def test_retention_keeps_the_newest_and_the_protected_snapshot(tmp_path: Path) -> None:
    snapshots = updater.Snapshots(tmp_path)
    for name in ("20260101", "20260102", "20260103", "20260104"):
        _snapshot(tmp_path, name)
    (tmp_path / "20260105.dump.partial").write_bytes(b"x")
    _snapshot(tmp_path, "20260100")
    (tmp_path / "20260100.dump").unlink()

    snapshots.prune(2, {"20260101"})

    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "20260101.dump",
        "20260101.json",
        "20260103.dump",
        "20260103.json",
        "20260104.dump",
        "20260104.json",
    ]


def test_an_unknown_journal_protocol_is_not_acted_on(tmp_path: Path) -> None:
    journal = updater.Journal(tmp_path / "journal.json")
    journal.path.write_text(json.dumps({"protocol": 3, "phase": "applying"}))

    with pytest.raises(updater.JournalUnreadable, match="protocol 3"):
        journal.load()


def test_atomic_writes_leave_no_temporary_files(tmp_path: Path) -> None:
    target = tmp_path / "file"
    updater.write_atomic(target, b"one", mode=0o600)
    updater.write_atomic(target, b"two", mode=0o640)

    assert target.read_bytes() == b"two"
    assert target.stat().st_mode & 0o777 == 0o640
    assert [p.name for p in tmp_path.iterdir()] == ["file"]
