import base64
import binascii
import csv
import hmac
import io
import json
import os
import stat
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, NoReturn
from urllib.parse import urlparse

import httpx
import pyzipper
import typer
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from helpers import (
    create_encrypted_zip,
    decrypt,
    decrypt_bytes,
    decrypt_user_private_key,
    encrypt,
    generate_entry_key,
    generate_key_derivation,
    generate_totp,
    unwrap_entry_key,
    wrap_entry_key,
)

app = typer.Typer(
    name="ciphermoth",
    help="Manage your self-hosted ciphermoth vault from the terminal.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
pw_app = typer.Typer(
    help="List, reveal, add, edit and delete vault entries.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
app.add_typer(pw_app, name="password")

_out = Console()
_err = Console(stderr=True)

_LABEL_WIDTH = 13
_KINDS = ("login", "note")
_CONFLICTS = ("skip", "overwrite")
_LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1")
_HISTORY_LIMIT = 20


@dataclass(frozen=True)
class CliSession:
    master_password: str
    headers: dict[str, str]
    vault_key: bytes
    private_key: bytes
    public_key: bytes


def _api_url() -> str:
    return os.environ.get("CIPHERMOTH_API_URL", "http://localhost:8000/api").rstrip("/")


def _die(msg: str) -> NoReturn:
    _err.print(f"[red]✗[/red]  {escape(msg)}")
    raise typer.Exit(1)


def _ok(msg: str) -> None:
    _out.print(f"[green]✓[/green]  {msg}")


def _check(resp: httpx.Response) -> None:
    if resp.is_success:
        return

    try:
        payload = resp.json()
        detail = payload.get("detail") or payload.get("error") or resp.text
    except ValueError:
        detail = resp.text

    if resp.status_code == 429:
        _die(
            f"{detail} Every command unlocks the vault once, so a batch of them "
            f"can hit this. Raise CIPHERMOTH_RATE_LIMIT on the backend to lift it."
        )

    _die(str(detail))


def _warn_plaintext_transport() -> None:
    parsed = urlparse(_api_url())
    host = parsed.hostname or ""
    if parsed.scheme == "https" or host in _LOCAL_HOSTS:
        return

    _err.print(
        f"[yellow]![/yellow]  {escape(host)} is reached over plain HTTP, so your "
        "authentication session crosses the network unencrypted. "
        "Put the API behind HTTPS."
    )


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _unlock(client: httpx.Client) -> CliSession:
    _warn_plaintext_transport()
    username = os.environ.get("CIPHERMOTH_USERNAME") or typer.prompt("Username")
    master = typer.prompt("Master password", hide_input=True)
    try:
        resp = client.post("/auth/challenge", json={"username": username})
    except httpx.ConnectError:
        _die(f"Cannot reach the API at {_api_url()!r}. Is the service running?")

    _check(resp)
    challenge = resp.json()
    vault_key = generate_key_derivation(_decode(challenge["salt"]), master)
    login_payload = {"challenge": challenge["challenge"]}
    if challenge.get("legacy_user"):
        private_bytes = decrypt_bytes(
            vault_key, challenge["encrypted_private_key"].encode()
        )
        if private_bytes is None:
            _die("Invalid username or master password.")
        try:
            private_key = X25519PrivateKey.from_private_bytes(private_bytes)
        except ValueError:
            _die("Invalid vault key.")
        shared = private_key.exchange(
            X25519PublicKey.from_public_bytes(_decode(challenge["nonce"]))
        )
        auth_private = Ed25519PrivateKey.generate()
        auth_private_bytes = auth_private.private_bytes(
            serialization.Encoding.DER,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        login_payload.update(
            signature=_encode(
                hmac.digest(shared, challenge["challenge"].encode(), "sha256")
            ),
            auth_public_key=_encode(
                auth_private.public_key().public_bytes(
                    serialization.Encoding.Raw, serialization.PublicFormat.Raw
                )
            ),
            encrypted_auth_private_key=encrypt(vault_key, auth_private_bytes).decode(),
        )
    else:
        encrypted_auth_private = challenge["encrypted_auth_private_key"].encode()
        auth_private_bytes = decrypt_bytes(vault_key, encrypted_auth_private)
        if auth_private_bytes is None:
            _die("Invalid username or master password.")
        auth_private = serialization.load_der_private_key(
            auth_private_bytes, password=None
        )
        if not isinstance(auth_private, Ed25519PrivateKey):
            _die("Invalid authentication key.")
        login_payload["signature"] = _encode(
            auth_private.sign(_decode(challenge["nonce"]))
        )
    resp = client.post("/auth/login", json=login_payload)
    _check(resp)
    data = resp.json()
    if data["user"].get("must_change_password"):
        _die("Change the temporary master password in the web UI first.")
    private_key = decrypt_user_private_key(
        vault_key, data["encrypted_private_key"].encode()
    )
    return CliSession(
        master_password=master,
        headers={"authorization": f"Bearer {data['token']}"},
        vault_key=vault_key,
        private_key=private_key,
        public_key=_decode(data["public_key"]),
    )


def _entry_key(session: CliSession, record: dict) -> bytes:
    context = (
        str(record["id"]).encode() if record.get("encryption_version") == 2 else b""
    )
    return unwrap_entry_key(
        session.private_key, _decode(record["wrapped_key"]), context
    )


def _decrypt_record(session: CliSession, record: dict) -> dict:
    key = _entry_key(session, record)
    payload = decrypt(key, record["encrypted_payload"].encode())
    if payload is None:
        _die(f"Could not decrypt entry #{record['id']}.")
    item = json.loads(payload)
    preferences = (
        decrypt(key, record["encrypted_preferences"].encode())
        if record.get("encrypted_preferences")
        else None
    )
    item.update(
        id=record["id"],
        owner_id=record["owner_id"],
        owner_username=str(record["owner_id"]),
        access=record["access"],
        favorite=(
            json.loads(preferences).get("favorite", False) if preferences else False
        ),
        updated=record.get("updated"),
        deleted=record.get("deleted"),
    )
    return item


def _encrypted_attachments(key: bytes, attachments: list[dict]) -> list[str]:
    if any(
        not isinstance(attachment, dict) or not isinstance(attachment.get("data"), str)
        for attachment in attachments
    ):
        _die("Backup contains an invalid attachment.")
    return [
        encrypt(key, json.dumps(attachment).encode()).decode()
        for attachment in attachments
    ]


def _encrypted_create(session: CliSession, item: dict) -> dict[str, object]:
    key = generate_entry_key()
    favorite = bool(item.pop("favorite", False))
    attachments = item.pop("attachments", [])
    return {
        "encrypted_payload": encrypt(key, json.dumps(item).encode()).decode(),
        "wrapped_key": _encode(wrap_entry_key(session.public_key, key)),
        "encrypted_preferences": encrypt(
            key, json.dumps({"favorite": favorite}).encode()
        ).decode(),
        "encrypted_attachments": _encrypted_attachments(key, attachments),
    }


def _encrypted_update(
    session: CliSession, record: dict, item: dict, *, restoring: bool = False
) -> dict[str, object]:
    item = item.copy()
    attachments = item.pop("attachments", None)
    current = _decrypt_record(session, record)
    history = list(item.get("password_history", current.get("password_history", [])))
    if (
        not restoring
        and item.get("kind", current.get("kind")) == "login"
        and item.get("password_value") != current.get("password_value")
    ):
        history.append(
            {
                "value": current["password_value"],
                "changed_at": datetime.now(UTC).isoformat(),
            }
        )
        history = history[-_HISTORY_LIMIT:]
    item["password_history"] = history
    key = _entry_key(session, record)
    result: dict[str, object] = {
        "encrypted_payload": encrypt(key, json.dumps(item).encode()).decode()
    }
    if restoring:
        result["encrypted_preferences"] = encrypt(
            key, json.dumps({"favorite": bool(item.get("favorite", False))}).encode()
        ).decode()
        if attachments is not None:
            result["encrypted_attachments"] = _encrypted_attachments(key, attachments)
    return result


def _encrypted_preferences(
    session: CliSession, record: dict, favorite: bool
) -> dict[str, str]:
    return {
        "encrypted_preferences": encrypt(
            _entry_key(session, record),
            json.dumps({"favorite": favorite}).encode(),
        ).decode()
    }


def _decrypt_attachment(session: CliSession, record: dict, attachment: dict) -> dict:
    value = decrypt(_entry_key(session, record), attachment["encrypted_payload"])
    if value is None:
        _die("Attachment payload is empty.")
    payload = json.loads(value)
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), str):
        _die("Attachment payload is invalid.")
    return payload


def _get_records(client: httpx.Client, session: CliSession, path: str) -> list[dict]:
    legacy = client.get("/passwords/legacy", headers=session.headers)
    _check(legacy)
    if legacy.json():
        _die("Legacy entries must be migrated once in the web UI before using the CLI.")
    response = client.get(path, headers=session.headers)
    _check(response)
    return response.json()


def _entry_path(password_id: int, suffix: str = "") -> str:
    return f"/passwords/{password_id}{suffix}"


def _optional(label: str, current: str | None = None) -> str | None:
    return (
        typer.prompt(label, default=current or "", show_default=bool(current)) or None
    )


def _prompt_secret(label: str) -> str:
    return typer.prompt(label, hide_input=True, confirmation_prompt=True)


def _prompt_optional_secret(label: str) -> str | None:
    value = typer.prompt(label, hide_input=True, default="", show_default=False)
    if not value:
        return None

    if typer.prompt("Repeat for confirmation", hide_input=True) != value:
        _die("The two entries did not match.")

    return value


def _totp_code(secret: str) -> str:
    try:
        return generate_totp(secret)
    except (binascii.Error, ValueError):
        return "unreadable 2FA secret"


def _detail_rows(item: dict) -> list[tuple[str, str]]:
    rows = [("Note" if item.get("kind") == "note" else "Value", item["password_value"])]

    for label, key in (("Username", "username"), ("URL", "url")):
        if item.get(key):
            rows.append((label, item[key]))

    if item.get("totp_secret"):
        rows.append(("2FA code", _totp_code(item["totp_secret"])))

    if item.get("folder"):
        rows.append(("Folder", item["folder"]))

    if item.get("tags"):
        rows.append(("Tags", ", ".join(item["tags"])))

    for field in item.get("custom_fields") or []:
        shown = "••••••••" if field.get("hidden") else field.get("value", "")
        rows.append((field["label"], shown))

    if item.get("description"):
        rows.append(("Description", item["description"]))

    return rows


def _print_details(item: dict) -> None:
    rows = _detail_rows(item)
    width = max([_LABEL_WIDTH, *(len(label) + 2 for label, _ in rows)])

    _out.print(f"\n  [bold cyan]{escape(item['password_name'])}[/bold cyan]")

    for label, value in rows:
        head, *rest = str(value).split("\n")
        padding = " " * (width - len(label))
        _out.print(f"  [dim]{escape(label)}[/dim]{padding}{escape(head)}")
        for line in rest:
            _out.print(f"  {' ' * width}{escape(line)}")

    _out.print()


@pw_app.command("list", help="List every entry in the vault.")
def pw_list() -> None:
    with httpx.Client(
        base_url=_api_url(), timeout=30, follow_redirects=False
    ) as client:
        session = _unlock(client)
        records = _get_records(client, session, "/passwords")

    items = [_decrypt_record(session, record) for record in records]
    if not items:
        _out.print("[dim]The vault is empty.[/dim]")
        return

    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 2, 0, 0))
    table.add_column("ID", justify="right", style="dim")
    table.add_column("Name", style="cyan")
    table.add_column("Owner", style="dim")
    table.add_column("Access", style="dim")
    table.add_column("Description", style="dim")
    table.add_column("Backed up", justify="center")

    for item in items:
        table.add_row(
            str(item["id"]),
            escape(item["password_name"]),
            escape(item["owner_username"]),
            escape(item["access"]),
            escape(item.get("description") or "-"),
            "[green]✓[/green]" if item["backed_up"] else "[dim]–[/dim]",
        )

    _out.print(table)


@pw_app.command("get", help="Reveal one entry, including its live 2FA code.")
def pw_get(password_id: Annotated[int, typer.Argument(help="Entry ID.")]) -> None:
    with httpx.Client(
        base_url=_api_url(), timeout=30, follow_redirects=False
    ) as client:
        session = _unlock(client)
        resp = client.get(_entry_path(password_id), headers=session.headers)

    _check(resp)

    _print_details(_decrypt_record(session, resp.json()))


@pw_app.command(
    "create", help="Add a login or a secure note, prompting for each field."
)
def pw_create(
    name: Annotated[str, typer.Argument(help="Name for the new entry.")],
    kind: Annotated[
        str, typer.Option("--kind", "-k", help="Entry type: login or note.")
    ] = "login",
) -> None:
    if kind not in _KINDS:
        _die("--kind must be 'login' or 'note'.")

    is_note = kind == "note"

    with httpx.Client(
        base_url=_api_url(), timeout=30, follow_redirects=False
    ) as client:
        session = _unlock(client)

        value = _prompt_secret("Note body" if is_note else "Password value")
        username = None if is_note else _optional("Username / email")
        url = None if is_note else _optional("URL")
        totp_secret = None if is_note else _optional("TOTP secret")
        description = _optional("Description")
        folder = _optional("Folder")
        resp = client.post(
            "/passwords",
            json=_encrypted_create(
                session,
                {
                    "password_name": name,
                    "kind": kind,
                    "username": username,
                    "password_value": value,
                    "url": url,
                    "totp_secret": totp_secret,
                    "description": description,
                    "folder": folder,
                    "tags": [],
                    "custom_fields": [],
                    "favorite": False,
                },
            ),
            headers=session.headers,
        )

    _check(resp)

    _ok(f"Created [cyan]{escape(name)}[/cyan]")


@pw_app.command(
    "update",
    help="Edit an entry. Leave a prompt blank to keep the current value.",
)
def pw_update(
    password_id: Annotated[int, typer.Argument(help="Entry ID.")],
) -> None:
    with httpx.Client(
        base_url=_api_url(), timeout=30, follow_redirects=False
    ) as client:
        session = _unlock(client)

        current_resp = client.get(_entry_path(password_id), headers=session.headers)

        _check(current_resp)

        record = current_resp.json()
        current = _decrypt_record(session, record)
        is_note = current.get("kind") == "note"

        secret_label = "New note" if is_note else "New password value"
        new_value = (
            _prompt_optional_secret(f"{secret_label} (blank to keep the current one)")
            or current["password_value"]
        )
        new_username = (
            None if is_note else _optional("Username / email", current.get("username"))
        )
        new_url = None if is_note else _optional("URL", current.get("url"))
        new_totp = (
            None if is_note else _optional("TOTP secret", current.get("totp_secret"))
        )
        new_description = _optional("Description", current.get("description"))
        new_folder = _optional("Folder", current.get("folder"))

        shared = {
            "password_name": current["password_name"],
            "kind": current.get("kind", "login"),
            "tags": current.get("tags", []),
            "custom_fields": current.get("custom_fields", []),
            "favorite": current.get("favorite", False),
        }
        resp = client.put(
            _entry_path(password_id),
            json=_encrypted_update(
                session,
                record,
                {
                    **shared,
                    "username": new_username,
                    "password_value": new_value,
                    "url": new_url,
                    "totp_secret": new_totp,
                    "description": new_description,
                    "folder": new_folder,
                },
            ),
            headers=session.headers,
        )

    _check(resp)

    _ok(f"Updated entry [cyan]#{password_id}[/cyan]")


@pw_app.command("delete", help="Move an entry to the trash. It can be restored later.")
def pw_delete(
    password_id: Annotated[int, typer.Argument(help="Entry ID.")],
    yes: Annotated[
        bool, typer.Option("--yes", "-y", help="Skip confirmation.")
    ] = False,
) -> None:
    with httpx.Client(
        base_url=_api_url(), timeout=30, follow_redirects=False
    ) as client:
        session = _unlock(client)

        if not yes:
            typer.confirm(f"Move entry #{password_id} to trash?", abort=True)

        resp = client.delete(_entry_path(password_id), headers=session.headers)

    _check(resp)

    _ok(f"Moved entry [cyan]#{password_id}[/cyan] to trash")


@pw_app.command("trash", help="List the entries waiting in the trash.")
def pw_trash() -> None:
    with httpx.Client(
        base_url=_api_url(), timeout=30, follow_redirects=False
    ) as client:
        session = _unlock(client)
        records = _get_records(client, session, "/passwords/trash")

    items = [_decrypt_record(session, record) for record in records]
    if not items:
        _out.print("[dim]The trash is empty.[/dim]")
        return

    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 2, 0, 0))
    table.add_column("ID", justify="right", style="dim")
    table.add_column("Name", style="cyan")
    table.add_column("Description", style="dim")
    table.add_column("Deleted", style="dim")

    for item in items:
        table.add_row(
            str(item["id"]),
            escape(item["password_name"]),
            escape(item.get("description") or "-"),
            (item.get("deleted") or "-")[:19].replace("T", " "),
        )

    _out.print(table)


@pw_app.command(
    "restore", help="Move an entry out of the trash and back into the vault."
)
def pw_restore(password_id: Annotated[int, typer.Argument(help="Entry ID.")]) -> None:
    with httpx.Client(
        base_url=_api_url(), timeout=30, follow_redirects=False
    ) as client:
        session = _unlock(client)
        resp = client.post(
            _entry_path(password_id, "/restore"), headers=session.headers
        )

    _check(resp)

    _ok(f"Restored entry [cyan]#{password_id}[/cyan]")


@pw_app.command(
    "purge", help="Permanently delete a trashed entry. This cannot be undone."
)
def pw_purge(
    password_id: Annotated[int, typer.Argument(help="Entry ID.")],
    yes: Annotated[
        bool, typer.Option("--yes", "-y", help="Skip confirmation.")
    ] = False,
) -> None:
    if not yes:
        typer.confirm(f"Permanently delete entry #{password_id}?", abort=True)

    with httpx.Client(
        base_url=_api_url(), timeout=30, follow_redirects=False
    ) as client:
        session = _unlock(client)
        resp = client.delete(
            _entry_path(password_id, "/purge"), headers=session.headers
        )

    _check(resp)

    _ok(f"Permanently deleted entry [cyan]#{password_id}[/cyan]")


@app.command(
    "backup", help="Export the vault as a ZIP encrypted with your master password."
)
def cmd_backup(
    out_dir: Annotated[
        Path, typer.Option("--out", "-o", help="Directory to save the backup file.")
    ] = Path("."),
) -> None:
    with httpx.Client(
        base_url=_api_url(), timeout=60, follow_redirects=False
    ) as client:
        session = _unlock(client)
        records = _get_records(client, session, "/passwords")
        items = [_decrypt_record(session, record) for record in records]
        backup_entries = [
            {
                "name": item["password_name"],
                "kind": item.get("kind", "login"),
                "username": item.get("username"),
                "value": item["password_value"],
                "url": item.get("url"),
                "totp_secret": item.get("totp_secret"),
                "description": item.get("description"),
                "tags": item.get("tags", []),
                "custom_fields": item.get("custom_fields", []),
                "folder": item.get("folder"),
                "favorite": item.get("favorite", False),
                "password_history": item.get("password_history", []),
                "attachments": [
                    _decrypt_attachment(session, record, attachment)
                    for attachment in _get_records(
                        client,
                        session,
                        _entry_path(record["id"], "/attachments"),
                    )
                ],
            }
            for record, item in zip(records, items, strict=True)
        ]
        archive = create_encrypted_zip(backup_entries, session.master_password)
        for record, item in zip(records, items, strict=True):
            item["backed_up"] = True
            response = client.put(
                _entry_path(record["id"]),
                json=_encrypted_update(session, record, item),
                headers=session.headers,
            )
            _check(response)

    out_dir.mkdir(parents=True, exist_ok=True)
    filename = f"ciphermoth_backup_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.zip"
    dest = out_dir / filename
    dest.touch(mode=stat.S_IRUSR | stat.S_IWUSR)
    dest.chmod(stat.S_IRUSR | stat.S_IWUSR)
    dest.write_bytes(archive)

    _ok(f"Backup saved to [cyan]{escape(str(dest))}[/cyan]")


def _report_import(payload: dict) -> None:
    _ok(
        f"Import complete - "
        f"[cyan]{payload['imported']}[/cyan] added, "
        f"[cyan]{payload['overwritten']}[/cyan] overwritten, "
        f"[cyan]{payload['skipped']}[/cyan] skipped"
    )


def _read_import_file(file: Path, on_conflict: str) -> bytes:
    if not file.exists():
        _die(f"File not found: {file}")

    if on_conflict not in _CONFLICTS:
        _die("--on-conflict must be 'skip' or 'overwrite'.")

    return file.read_bytes()


def _backup_item(item: dict) -> dict:
    result = {
        "password_name": item.get("name"),
        "kind": item.get("kind", "login"),
        "username": item.get("username"),
        "password_value": item.get("value"),
        "url": item.get("url"),
        "totp_secret": item.get("totp_secret"),
        "description": item.get("description"),
        "tags": item.get("tags", []),
        "custom_fields": item.get("custom_fields", []),
        "folder": item.get("folder"),
        "favorite": item.get("favorite", False),
    }
    if isinstance(item.get("password_history"), list):
        result["password_history"] = item["password_history"]
    if isinstance(item.get("attachments"), list):
        result["attachments"] = item["attachments"]
    return result


def _read_backup(file_bytes: bytes, password: str) -> list[dict]:
    try:
        with pyzipper.AESZipFile(io.BytesIO(file_bytes)) as archive:
            archive.setpassword(password.encode())
            payload = json.loads(archive.read("ciphermoth_backup.json"))
    except (KeyError, ValueError, RuntimeError, pyzipper.BadZipFile) as exc:
        _die(f"Could not decrypt backup: {exc}")
    if not isinstance(payload.get("passwords"), list):
        _die("Invalid CipherMoth backup.")
    return [_backup_item(item) for item in payload["passwords"]]


def _csv_items(file_bytes: bytes) -> list[dict]:
    aliases = {
        "password_name": ("name", "title", "account", "login_name", "item name"),
        "username": ("username", "login_username", "user", "email", "login"),
        "password_value": ("password", "login_password", "pass"),
        "url": ("url", "uri", "login_uri", "website", "site"),
        "description": ("notes", "note", "description", "comment", "comments"),
        "folder": ("folder", "grouping", "group", "category", "collection"),
        "totp_secret": ("totp", "login_totp", "otpauth", "otp", "2fa"),
    }
    reader = csv.DictReader(io.StringIO(file_bytes.decode("utf-8-sig")))
    headers = {header.lower(): header for header in (reader.fieldnames or [])}

    def value(row: dict, field: str) -> str | None:
        source = next(
            (headers[name] for name in aliases[field] if name in headers), None
        )
        return row.get(source, "").strip() or None if source else None

    entries = []
    for row in reader:
        entries.append(
            {
                "password_name": value(row, "password_name"),
                "kind": "login",
                "username": value(row, "username"),
                "password_value": value(row, "password_value"),
                "url": value(row, "url"),
                "totp_secret": value(row, "totp_secret"),
                "description": value(row, "description"),
                "tags": [],
                "custom_fields": [],
                "folder": value(row, "folder"),
                "favorite": False,
            }
        )
    return entries


def _import_items(
    client: httpx.Client,
    session: CliSession,
    items: list[dict],
    on_conflict: str,
) -> dict[str, int]:
    records = _get_records(client, session, "/passwords")
    existing = {
        item["password_name"]: (record, item)
        for record in records
        for item in [_decrypt_record(session, record)]
    }
    result = {
        "imported": 0,
        "overwritten": 0,
        "skipped": 0,
        "total": len(items),
    }
    for item in items:
        name = item.get("password_name")
        if not name or not item.get("password_value"):
            _die("Import contains an entry without a name or password value.")
        current = existing.get(name)
        if current and on_conflict == "skip":
            result["skipped"] += 1
            continue
        if current:
            record, current_item = current
            updated_item = {**current_item, **item}
            response = client.put(
                _entry_path(record["id"]),
                json=_encrypted_update(session, record, updated_item, restoring=True),
                headers=session.headers,
            )
            _check(response)
            result["overwritten"] += 1
        else:
            response = client.post(
                "/passwords",
                json=_encrypted_create(session, item.copy()),
                headers=session.headers,
            )
            result["imported"] += 1
        _check(response)
    return result


@app.command("import", help="Restore entries from a CipherMoth backup ZIP.")
def cmd_import(
    file: Annotated[Path, typer.Argument(help="Path to the ciphermoth backup ZIP.")],
    on_conflict: Annotated[
        str,
        typer.Option(
            help="How to handle existing entries: skip or overwrite.",
        ),
    ] = "skip",
) -> None:
    file_bytes = _read_import_file(file, on_conflict)

    with httpx.Client(
        base_url=_api_url(), timeout=60, follow_redirects=False
    ) as client:
        session = _unlock(client)
        result = _import_items(
            client,
            session,
            _read_backup(file_bytes, session.master_password),
            on_conflict,
        )

    _report_import(result)


@app.command(
    "import-csv",
    help="Import a CSV exported from Chrome, Bitwarden, KeePass or Proton Pass.",
)
def cmd_import_csv(
    file: Annotated[
        Path, typer.Argument(help="Path to a CSV exported from another manager.")
    ],
    on_conflict: Annotated[
        str,
        typer.Option(
            help="How to handle existing entries: skip or overwrite.",
        ),
    ] = "skip",
) -> None:
    file_bytes = _read_import_file(file, on_conflict)

    with httpx.Client(
        base_url=_api_url(), timeout=60, follow_redirects=False
    ) as client:
        session = _unlock(client)
        result = _import_items(
            client,
            session,
            _csv_items(file_bytes),
            on_conflict,
        )

    _report_import(result)


if __name__ == "__main__":
    app()
