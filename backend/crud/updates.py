import json
import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from errors import Forbidden

_TAG_RE = re.compile(r"v(\d+)\.(\d+)\.(\d+)", re.ASCII)
_VERSION_RE = re.compile(r"v?(\d+)\.(\d+)\.(\d+)", re.ASCII)

_CONTROL_DIR = Path(os.environ.get("UPDATE_CONTROL_DIR", "/update-control"))
_REQUEST_FILE = _CONTROL_DIR / "request.json"
_RESULT_FILE = _CONTROL_DIR / "result.json"
_READY_FILE = _CONTROL_DIR / "updater.ready"

_TERMINAL = {"success", "failed", "rolled_back"}
_IN_PROGRESS = {"verifying", "applying"}


def _parse_version(value: str, pattern: re.Pattern[str]) -> tuple[int, ...] | None:
    match = pattern.fullmatch(value)
    return tuple(int(part) for part in match.groups()) if match else None


def _updater_present() -> bool:
    return _READY_FILE.exists()


def _write_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(payload, handle)
        os.replace(tmp, path)
    except Exception:
        Path(tmp).unlink(missing_ok=True)
        raise


def get_apply_status() -> dict:
    present = _updater_present()
    result: dict = {}
    if _RESULT_FILE.exists():
        try:
            result = json.loads(_RESULT_FILE.read_text())
        except (OSError, ValueError):
            result = {}

    state = result.get("state")
    if state not in _TERMINAL and state not in _IN_PROGRESS:
        state = "requested" if _REQUEST_FILE.exists() else "idle"

    return {
        "state": state,
        "detail": result.get("detail"),
        "target": result.get("target"),
        "finished_at": result.get("finished_at"),
        "updater_present": present,
    }


def request_update(target: str, current_version: str) -> dict:
    if not _updater_present():
        raise Forbidden("One-click updates are not enabled on this instance.")
    target_version = _parse_version(target, _TAG_RE)
    if target_version is None:
        raise Forbidden("Invalid release tag.")
    current = _parse_version(current_version, _VERSION_RE)
    if current is None or target_version <= current:
        raise Forbidden(
            f"Refusing to update: {target} is not newer than the running "
            f"version {current_version}."
        )

    _RESULT_FILE.unlink(missing_ok=True)
    _write_atomic(
        _REQUEST_FILE,
        {"target": target, "requested_at": datetime.now(UTC).isoformat()},
    )
    return get_apply_status()
