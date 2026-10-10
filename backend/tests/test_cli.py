import io
import json
import stat
from pathlib import Path

import httpx
import pytest
import pyzipper
from typer.testing import CliRunner, Result

from cli import app as cli_app
from tests.support import MASTER_PASSWORD, WRONG_MASTER_PASSWORD, db_execute

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
