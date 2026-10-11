import http.server
import io
import json
import os
import shutil
import stat
import subprocess
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
import pytest
import pyzipper
import typer
from cryptography.fernet import Fernet
from typer.testing import CliRunner, Result

from cli import app as cli_app
from helpers import encrypt
from tests.support import (
    MASTER_PASSWORD,
    WRONG_MASTER_PASSWORD,
    db_execute,
    db_snapshot,
)

runner = CliRunner()


@pytest.fixture
def api(live_server: str) -> str:
    resp = httpx.post(
        f"{live_server}/master_password/create",
        json={"master_password": MASTER_PASSWORD},
    )
    assert resp.status_code == 200, resp.text
    return live_server


def cli(api: str, *args: str, answers: list[str] | None = None) -> Result:
    lines = [MASTER_PASSWORD, *(answers or [])]
    return runner.invoke(
        cli_app,
        list(args),
        input="\n".join(lines) + "\n",
        env={"CIPHERMOTH_API_URL": api, "COLUMNS": "200"},
    )


def ok(result: Result) -> str:
    assert result.exit_code == 0, result.output
    return result.output


async def test_cli_entry_lifecycle(api: str) -> None:
    ok(
        cli(
            api,
            "password",
            "create",
            "Bank [main] #1",
            answers=[
                "Pa$$-[bold]w0rd",
                "Pa$$-[bold]w0rd",
                "moth@example.com",
                "https://bank.test",
                "JBSWY3DPEHPK3PXP",
                "checking",
                "Finance",
            ],
        )
    )
    ok(
        cli(
            api,
            "password",
            "create",
            "recovery codes",
            "--kind",
            "note",
            answers=["code-1 code-2", "code-1 code-2", "", ""],
        )
    )

    listing = ok(cli(api, "password", "list"))
    assert "Bank [main] #1" in listing
    assert "recovery codes" in listing

    details = ok(cli(api, "password", "get", "Bank [main] #1"))
    assert "Pa$$-[bold]w0rd" in details
    assert "moth@example.com" in details
    assert "Finance" in details
    assert "2FA code" in details

    ok(
        cli(
            api,
            "password",
            "update",
            "Bank [main] #1",
            answers=["New-Pass-2", "New-Pass-2", "", "", "", "", ""],
        )
    )
    details = ok(cli(api, "password", "get", "Bank [main] #1"))
    assert "New-Pass-2" in details
    assert "moth@example.com" in details

    ok(cli(api, "password", "delete", "Bank [main] #1", "--yes"))
    assert "Bank [main] #1" in ok(cli(api, "password", "trash"))
    assert "Bank [main] #1" not in ok(cli(api, "password", "list"))
    ok(cli(api, "password", "restore", "Bank [main] #1"))
    assert "New-Pass-2" in ok(cli(api, "password", "get", "Bank [main] #1"))

    ok(cli(api, "password", "delete", "recovery codes", "--yes"))
    ok(cli(api, "password", "purge", "recovery codes", "--yes"))
    assert "The trash is empty" in ok(cli(api, "password", "trash"))


async def test_cli_backup_import_and_csv(api: str, tmp_path: Path) -> None:
    ok(
        cli(
            api,
            "password",
            "create",
            "mail",
            answers=["mail-Pass-1", "mail-Pass-1", "", "", "", "", ""],
        )
    )
    ok(cli(api, "backup", "--out", str(tmp_path)))
    [archive] = list(tmp_path.glob("ciphermoth_backup_*.zip"))
    assert stat.S_IMODE(archive.stat().st_mode) == 0o600
    with pyzipper.AESZipFile(io.BytesIO(archive.read_bytes())) as zf:
        zf.setpassword(MASTER_PASSWORD.encode())
        names = [
            p["name"]
            for p in json.loads(zf.read("ciphermoth_backup.json"))["passwords"]
        ]
    assert names == ["mail"]

    ok(cli(api, "password", "delete", "mail", "--yes"))
    ok(cli(api, "password", "purge", "mail", "--yes"))
    assert "1 added" in ok(cli(api, "import", str(archive)))
    assert "mail-Pass-1" in ok(cli(api, "password", "get", "mail"))

    csv_file = tmp_path / "export.csv"
    csv_file.write_text("name,password\nmail,csv-Pass-2\nshop,shop-Pass-3\n")
    output = ok(cli(api, "import-csv", str(csv_file), "--on-conflict", "overwrite"))
    assert "1 added" in output
    assert "1 overwritten" in output
    assert "csv-Pass-2" in ok(cli(api, "password", "get", "mail"))


async def test_cli_rejects_a_wrong_master_password(live_server: str) -> None:
    httpx.post(
        f"{live_server}/master_password/create",
        json={"master_password": MASTER_PASSWORD},
    )
    result = runner.invoke(
        cli_app,
        ["password", "list"],
        input=WRONG_MASTER_PASSWORD + "\n",
        env={"CIPHERMOTH_API_URL": live_server},
    )
    assert result.exit_code == 1
    assert "Invalid master password" in result.output


async def test_cli_works_on_a_vault_upgraded_from_v145(api: str) -> None:
    ok(
        cli(
            api,
            "password",
            "create",
            "legacy",
            answers=["legacy-Pass-1", "legacy-Pass-1", "", "", "", "", ""],
        )
    )
    await db_execute("UPDATE master_password SET key_check = NULL")

    assert "legacy" in ok(cli(api, "password", "list"))
    rows = await db_execute("SELECT key_check FROM master_password")
    assert rows[0][0] is not None


async def test_live_server_logs_do_not_contain_secrets(
    api: str, live_server_log: Path
) -> None:
    ok(
        cli(
            api,
            "password",
            "create",
            "log-canary-entry",
            answers=["log-canary-Value", "log-canary-Value", "", "", "", "", ""],
        )
    )
    ok(cli(api, "password", "get", "log-canary-entry"))
    log = live_server_log.read_text(errors="replace")
    assert "log-canary-Value" not in log
    assert MASTER_PASSWORD not in log
    assert "log-canary-entry" not in log
    assert '"GET /api/passwords/{password_name} HTTP/1.1" 200' in log


async def test_cli_can_remove_an_entry_it_cannot_decrypt(api: str) -> None:
    ok(
        cli(
            api,
            "password",
            "create",
            "good",
            answers=["good-Pass-1", "good-Pass-1", "", "", "", "", ""],
        )
    )
    await db_execute(
        "INSERT INTO passwords (password_name, password_value) VALUES (:n, :v)",
        n="planted",
        v=encrypt(Fernet.generate_key(), b"written with another key"),
    )
    assert cli(api, "password", "list").exit_code == 1

    ok(cli(api, "password", "delete", "planted", "--yes"))
    ok(cli(api, "password", "purge", "planted", "--yes"))
    assert "good" in ok(cli(api, "password", "list"))

    missing = cli(api, "password", "delete", "never-existed", "--yes")
    assert missing.exit_code == 1
    assert "No password found" in missing.output


FULL_ENTRY = {
    "password_name": "full",
    "kind": "login",
    "username": "moth@example.com",
    "password_value": "full-Value-1",
    "url": "https://full.test",
    "totp_secret": "JBSWY3DPEHPK3PXP",
    "description": "every field",
    "tags": ["one", "two"],
    "custom_fields": [
        {"label": "PIN", "value": "1234", "hidden": True},
        {"label": "Account", "value": "42", "hidden": False},
    ],
    "folder": "Finance",
    "favorite": True,
}
NOTE_ENTRY = {
    "password_name": "note",
    "kind": "note",
    "password_value": "  body line\n\n",
    "description": "a note",
    "tags": ["n"],
    "custom_fields": [{"label": "ref", "value": "x", "hidden": False}],
    "folder": "Notes",
    "favorite": True,
}
COMPARED = (
    "kind",
    "username",
    "password_value",
    "url",
    "totp_secret",
    "description",
    "tags",
    "custom_fields",
    "folder",
    "favorite",
    "password_history",
)


def _key(api: str) -> str:
    resp = httpx.post(
        f"{api}/master_password/check", json={"master_password": MASTER_PASSWORD}
    )
    return resp.json()["key_derivation"]


def _api_create(api: str, item: dict) -> None:
    resp = httpx.post(
        f"{api}/passwords/create",
        json=item,
        headers={"x-ciphermoth-key-derivation": _key(api)},
    )
    assert resp.status_code == 200, resp.text


def _api_get(api: str, name: str) -> dict:
    resp = httpx.get(
        f"{api}/passwords/{quote(name, safe='')}",
        headers={"x-ciphermoth-key-derivation": _key(api)},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.mark.parametrize("item", [FULL_ENTRY, NOTE_ENTRY], ids=["login", "note"])
async def test_cli_update_with_blank_answers_changes_nothing(
    api: str, item: dict
) -> None:
    _api_create(api, item)
    before = _api_get(api, item["password_name"])
    prompts = 3 if item["kind"] == "note" else 6

    ok(cli(api, "password", "update", item["password_name"], answers=[""] * prompts))

    after = _api_get(api, item["password_name"])
    assert {f: after[f] for f in COMPARED} == {f: before[f] for f in COMPARED}


async def test_cli_update_changes_only_what_was_typed(api: str) -> None:
    _api_create(api, FULL_ENTRY)

    ok(
        cli(
            api,
            "password",
            "update",
            "full",
            answers=["full-Value-2", "full-Value-2", "", "", "", "new description", ""],
        )
    )

    after = _api_get(api, "full")
    assert after["password_value"] == "full-Value-2"
    assert after["description"] == "new description"
    assert [h["value"] for h in after["password_history"]] == ["full-Value-1"]
    for field in ("username", "url", "totp_secret", "tags", "custom_fields"):
        assert after[field] == FULL_ENTRY[field]
    assert after["folder"] == "Finance"
    assert after["favorite"] is True


HOSTILE_NAMES = [
    "notes#2024",
    "a?b=c&d",
    "50% off",
    ".",
    "..",
    "...",
    "space  name ",
    "ünï 🦋",
    "[bold]markup[bold]",
    "back\\slash",
]


@pytest.mark.parametrize("name", HOSTILE_NAMES)
async def test_cli_reaches_exactly_the_named_entry(api: str, name: str) -> None:
    for decoy in ("notes", "a", "50", "escape", "decoy"):
        _api_create(api, {"password_name": decoy, "password_value": f"{decoy}-v"})
    _api_create(api, {"password_name": name, "password_value": "target-Value-1"})
    stored = name.strip()

    assert "target-Value-1" in ok(cli(api, "password", "get", stored))
    ok(cli(api, "password", "delete", stored, "--yes"))

    rows = await db_execute(
        "SELECT password_name FROM passwords WHERE deleted IS NOT NULL"
    )
    assert rows == [(stored,)]


@pytest.mark.parametrize(
    ("name", "command"),
    [
        ("a/b", ["get"]),
        ("a/b", ["delete", "--yes"]),
        ("x/purge", ["delete", "--yes"]),
        ("x/restore", ["restore"]),
        ("x/attachments/1", ["delete", "--yes"]),
        ("../x", ["delete", "--yes"]),
    ],
)
async def test_cli_names_with_a_slash_never_reach_another_entry(
    api: str, name: str, command: list[str]
) -> None:
    _api_create(api, {"password_name": "x", "password_value": "x-Value-1"})
    key = {"x-ciphermoth-key-derivation": _key(api)}
    httpx.post(
        f"{api}/passwords/x/attachments",
        files={"file": ("f.bin", b"keep me", "application/octet-stream")},
        headers=key,
    )
    _api_create(api, {"password_name": "trashed", "password_value": "t-v"})
    httpx.delete(f"{api}/passwords/trashed", headers=key)
    _api_create(api, {"password_name": name, "password_value": "slash-v"})
    before = await db_snapshot()

    result = cli(api, "password", command[0], name, *command[1:])

    assert result.exit_code == 1, result.output
    assert "contain" in result.output and "/" in result.output
    assert await db_snapshot() == before


async def test_cli_prints_markup_in_stored_values_literally(api: str) -> None:
    markup = "[red]x[/red] [/] [link=https://evil.test]click[/link] [bold"
    name = "markup [red]x[red] [bold"
    _api_create(
        api,
        {
            "password_name": name,
            "password_value": "v " + markup,
            "username": "u " + markup,
            "url": "https://x.test/" + markup,
            "description": "d " + markup,
            "folder": "f " + markup,
            "tags": ["t [red]x[/red] [/]"],
            "custom_fields": [{"label": "l " + markup, "value": "c " + markup}],
        },
    )

    details = ok(cli(api, "password", "get", name))
    for prefix in ("v", "u", "d", "f", "l", "c"):
        assert f"{prefix} {markup}" in details
    assert "t [red]x[/red] [/]" in details
    listing = ok(cli(api, "password", "list"))
    assert name in listing


async def test_cli_masks_hidden_custom_fields(api: str) -> None:
    _api_create(api, FULL_ENTRY)
    details = ok(cli(api, "password", "get", "full"))
    assert "1234" not in details
    assert "••••••••" in details
    assert "42" in details


async def test_cli_never_echoes_the_master_password(api: str, tmp_path: Path) -> None:
    _api_create(api, FULL_ENTRY)
    outputs = [
        cli(api, "password", "list").output,
        cli(api, "password", "get", "full").output,
        cli(api, "backup", "--out", str(tmp_path)).output,
    ]
    for output in outputs:
        assert MASTER_PASSWORD not in output


def test_cli_takes_no_secret_as_an_argument_or_option() -> None:
    command = typer.main.get_command(cli_app)
    forbidden = ("password", "secret", "master", "key", "totp", "value", "token")

    def walk(cmd: Any, path: str) -> list[str]:
        found = [
            f"{path} {p.name}"
            for p in cmd.params
            if any(word in (p.name or "").lower() for word in forbidden)
        ]
        for name, sub in getattr(cmd, "commands", {}).items():
            found += walk(sub, f"{path} {name}")
        return found

    assert walk(command, "ciphermoth") == []


class _Recorder(http.server.BaseHTTPRequestHandler):
    requests: list[tuple[str, str, dict]] = []
    respond: Callable[["_Recorder"], None] = staticmethod(lambda handler: None)

    def _handle(self) -> None:
        self.rfile.read(int(self.headers.get("content-length") or 0))
        type(self).requests.append((self.command, self.path, dict(self.headers)))
        type(self).respond(self)

    do_GET = do_POST = do_PATCH = do_DELETE = _handle

    def log_message(self, format: str, *args: Any) -> None:
        return

    def send(self, status: int, payload: object, **headers: str) -> None:
        data = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.send_response(status)
        for name, value in headers.items():
            self.send_header(name, value)
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


@contextmanager
def _fake_server(respond: Callable[[_Recorder], None]) -> Iterator[tuple[str, list]]:
    handler = type(
        "Handler", (_Recorder,), {"requests": [], "respond": staticmethod(respond)}
    )
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/api", handler.requests
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.parametrize("redirect_check", [False, True])
def test_cli_never_follows_redirects_with_the_key_or_password(
    redirect_check: bool,
) -> None:
    with _fake_server(lambda handler: handler.send(200, [])) as (evil, evil_requests):

        def respond(handler: _Recorder) -> None:
            if redirect_check or not handler.path.endswith("/master_password/check"):
                handler.send(
                    307, b"", location=f"{evil.removesuffix('/api')}{handler.path}"
                )
            else:
                handler.send(200, {"valid": True, "key_derivation": "K" * 43 + "="})

        with _fake_server(respond) as (api, _):
            result = runner.invoke(
                cli_app,
                ["password", "list"],
                input=MASTER_PASSWORD + "\n",
                env={"CIPHERMOTH_API_URL": api},
            )

    assert result.exit_code == 1
    assert evil_requests == []


@pytest.mark.parametrize(
    ("status", "payload", "expected"),
    [
        (
            403,
            {
                "detail": "Invalid or expired vault key. [Unlock] again.",
                "code": "invalid_key",
            },
            "[Unlock] again",
        ),
        (400, {"error": "legacy [error] shape"}, "legacy [error] shape"),
        (500, b"plain [text] failure", "plain [text] failure"),
        (429, {"detail": "Too many attempts."}, "CIPHERMOTH_RATE_LIMIT"),
    ],
)
def test_cli_reports_server_errors_readably(
    status: int, payload: object, expected: str
) -> None:
    def respond(handler: _Recorder) -> None:
        if handler.path.endswith("/master_password/check"):
            handler.send(200, {"valid": True, "key_derivation": "K" * 43 + "="})
        else:
            handler.send(status, payload, **{"content-type": "application/json"})

    with _fake_server(respond) as (api, _):
        result = runner.invoke(
            cli_app,
            ["password", "list"],
            input=MASTER_PASSWORD + "\n",
            env={"CIPHERMOTH_API_URL": api, "COLUMNS": "200"},
        )

    assert result.exit_code == 1
    assert expected in result.output
    assert "Traceback" not in result.output


@pytest.mark.parametrize(
    ("url", "warned"),
    [
        ("http://vault.example.invalid:9/api", True),
        ("https://vault.example.invalid:9/api", False),
        ("http://localhost:9/api", False),
        ("http://127.0.0.1:9/api", False),
    ],
)
def test_cli_warns_before_sending_the_master_password_over_plain_http(
    url: str, warned: bool
) -> None:
    result = runner.invoke(
        cli_app,
        ["password", "list"],
        input=MASTER_PASSWORD + "\n",
        env={"CIPHERMOTH_API_URL": url},
    )
    assert result.exit_code == 1
    assert ("plain HTTP" in result.output) is warned
    assert "Cannot reach the API" in result.output or "Traceback" not in result.output


CIP = Path(__file__).resolve().parents[2] / "scripts" / "cip"


def _cip(
    tmp_path: Path, *args: str, running: bool = True
) -> tuple[int, str, list[str]]:
    home = tmp_path / "install"
    bin_dir = tmp_path / "bin"
    home.mkdir(exist_ok=True)
    bin_dir.mkdir(exist_ok=True)
    (home / "docker-compose.prod.yml").write_text("services: {}\n")
    shutil.copy(CIP, home / "cip")
    calls = tmp_path / "calls"
    docker = bin_dir / "docker"
    docker.write_text(
        "#!/bin/sh\n"
        'if [ "$4" = "ps" ]; then '
        + ("echo backend; " if running else "")
        + "exit 0; fi\n"
        f'for arg in "$@"; do printf "%s\\0" "$arg" >> "{calls}"; done\n'
    )
    docker.chmod(0o755)
    link = tmp_path / "cip-link"
    if not link.exists():
        link.symlink_to(home / "cip")
    result = subprocess.run(
        ["sh", str(link), *args],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env={**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"},
        timeout=30,
    )
    recorded = calls.read_bytes().split(b"\0")[:-1] if calls.exists() else []
    return result.returncode, result.stderr, [a.decode() for a in recorded]


@pytest.mark.skipif(shutil.which("sh") is None, reason="needs a POSIX shell")
def test_cip_passes_arguments_through_verbatim(tmp_path: Path) -> None:
    hostile = ["password", "get", "name with spaces; rm -rf / $(id) `id` \"q\" 'q' *"]

    code, stderr, calls = _cip(tmp_path, *hostile)

    assert code == 0, stderr
    compose = str((tmp_path / "install" / "docker-compose.prod.yml").resolve())
    assert (
        calls[-len(hostile) - 7 :]
        == [
            "compose",
            "-f",
            compose,
            "exec",
            "backend",
            "ciphermoth",
            *hostile,
        ][-len(hostile) - 7 :]
    )


@pytest.mark.skipif(shutil.which("sh") is None, reason="needs a POSIX shell")
def test_cip_refuses_when_the_backend_is_not_running(tmp_path: Path) -> None:
    code, stderr, calls = _cip(tmp_path, "password", "list", running=False)
    assert code == 1
    assert "isn't running" in stderr
    assert calls == []
