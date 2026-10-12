import json
import os
import re
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

from errors import Forbidden
from update_protocol import (
    HEARTBEAT_MAX_AGE_SECONDS,
    RECREATE_UPDATER_COMMAND,
    REQUIRED_UPDATER_PROTOCOL,
)

_TAG_RE = re.compile(r"v(\d+)\.(\d+)\.(\d+)", re.ASCII)
_VERSION_RE = re.compile(r"v?(\d+)\.(\d+)\.(\d+)", re.ASCII)

_TERMINAL = {"success", "failed", "rolled_back"}
_IN_PROGRESS = {
    "verifying",
    "snapshotting",
    "applying",
    "validating",
    "rolling_back",
}
_ATTENTION = "intervention"


def _control_dir() -> Path:
    return Path(os.environ.get("UPDATE_CONTROL_DIR", "/update-control"))


def _request_file() -> Path:
    return _control_dir() / "request.json"


def _result_file() -> Path:
    return _control_dir() / "result.json"


def _maintenance_file() -> Path:
    return _control_dir() / "maintenance.json"


def _parse_version(value: str, pattern: re.Pattern[str]) -> tuple[int, ...] | None:
    match = pattern.fullmatch(value)
    return tuple(int(part) for part in match.groups()) if match else None


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def maintenance_active() -> bool:
    return os.path.lexists(_maintenance_file())


def updater_info(now: datetime | None = None) -> dict:
    heartbeat = _read_json(_control_dir() / "updater.json")
    protocol = heartbeat.get("protocol")
    if isinstance(protocol, int) and not isinstance(protocol, bool):
        version = heartbeat.get("version")
        alive = False
        try:
            beat = datetime.fromisoformat(str(heartbeat.get("heartbeat_at")))
            if beat.tzinfo is None:
                beat = beat.replace(tzinfo=UTC)
            age = ((now or datetime.now(UTC)) - beat).total_seconds()
            alive = heartbeat.get("running") is not False and (
                -HEARTBEAT_MAX_AGE_SECONDS <= age <= HEARTBEAT_MAX_AGE_SECONDS
            )
        except ValueError:
            alive = False
        return {
            "present": alive,
            "protocol": protocol,
            "version": version if isinstance(version, str) else None,
        }
    if (_control_dir() / "updater.ready").exists():
        return {"present": True, "protocol": 1, "version": None}
    return {"present": False, "protocol": None, "version": None}


def _publish_request(payload: dict) -> None:
    request = _request_file()
    fd, tmp = tempfile.mkstemp(dir=request.parent)
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(payload, handle)
        os.chmod(tmp, 0o644)
        try:
            os.link(tmp, request)
        except FileExistsError as error:
            raise Forbidden("An update request is already waiting.") from error
    finally:
        Path(tmp).unlink(missing_ok=True)


def get_apply_status() -> dict:
    info = updater_info()
    result = _read_json(_result_file())
    state = result.get("state")
    if state not in _TERMINAL and state not in _IN_PROGRESS and state != _ATTENTION:
        state = "idle"
    if state not in _IN_PROGRESS and _request_file().exists():
        state = "requested"
    protocol = info["protocol"]
    return {
        "state": state,
        "detail": result.get("detail"),
        "target": result.get("target"),
        "finished_at": result.get("finished_at"),
        "id": result.get("id"),
        "updater_present": info["present"],
        "updater_protocol": protocol,
        "updater_version": info["version"],
        "updater_upgrade_required": protocol is not None
        and protocol < REQUIRED_UPDATER_PROTOCOL,
        "required_protocol": REQUIRED_UPDATER_PROTOCOL,
        "maintenance": maintenance_active(),
    }


def request_update(target: str, current_version: str) -> dict:
    info = updater_info()
    if info["protocol"] is not None and info["protocol"] < REQUIRED_UPDATER_PROTOCOL:
        raise Forbidden(
            "One-click updates need the new updater first, because the one "
            "running here cannot restore the database if an update fails. Run "
            f"this once in your CipherMoth folder: {RECREATE_UPDATER_COMMAND}"
        )
    if not info["present"]:
        if info["protocol"] is not None:
            raise Forbidden(
                "The updater is not running. Start it with: docker compose -f "
                "docker-compose.prod.yml --profile autoupdate up -d updater"
            )
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
    status = get_apply_status()
    if status["state"] == _ATTENTION:
        raise Forbidden(
            "A previous update needs manual attention first; see the updater's "
            "logs and 'Manual recovery' in docs/UPDATING.md."
        )
    if status["state"] in _IN_PROGRESS or status["maintenance"]:
        raise Forbidden("An update is already in progress.")

    if _request_file().exists():
        raise Forbidden("An update request is already waiting.")
    request_id = uuid.uuid4().hex
    _publish_request(
        {
            "target": target,
            "id": request_id,
            "requested_at": datetime.now(UTC).isoformat(),
        }
    )
    if _read_json(_result_file()).get("state") in _TERMINAL:
        _result_file().unlink(missing_ok=True)
    return {**get_apply_status(), "request_id": request_id}
