import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, fields
from datetime import datetime
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncConnection

from helpers import verify_key_check, verify_master_password

ENCRYPTED_COLUMNS = {
    "passwords": (
        "password_value",
        "url",
        "totp_secret",
        "tags",
        "custom_fields",
        "folder",
        "password_history",
    ),
    "password_attachments": ("filename", "content", "content_type"),
}
KINDS = ("login", "note")


@dataclass(frozen=True)
class Problem:
    table: str
    row_id: object
    column: str
    reason: str

    def __str__(self) -> str:
        return f"{self.table}[{self.row_id}].{self.column}: {self.reason}"


class VaultIntegrityError(AssertionError):
    def __init__(self, problems: list[Problem]) -> None:
        self.problems = problems
        super().__init__(
            f"{len(problems)} integrity problem(s):\n"
            + "\n".join(f"  {p}" for p in problems)
        )


@dataclass(frozen=True)
class Attachment:
    id: int
    filename: str
    content_type: str | None
    size_bytes: int
    sha256: str
    created: datetime | None

    @property
    def identity(self) -> tuple:
        return (self.filename, self.content_type, self.size_bytes, self.sha256)


@dataclass(frozen=True)
class Entry:
    id: int
    name: str
    kind: str
    username: str | None
    description: str | None
    value: str
    url: str | None
    totp_secret: str | None
    tags: tuple[str, ...]
    custom_fields: tuple[tuple[str, str, bool], ...]
    folder: str | None
    history: tuple[tuple[str, str], ...]
    favorite: bool
    backed_up: bool
    created: datetime | None
    updated: datetime | None
    deleted: datetime | None
    attachments: tuple[Attachment, ...]

    @property
    def trashed(self) -> bool:
        return self.deleted is not None


@dataclass(frozen=True)
class VaultContents:
    revision: str | None
    master_rows: int
    key_check: str
    entries: tuple[Entry, ...]
    settings: tuple[Mapping[str, object], ...]
    problems: tuple[Problem, ...] = field(default=())

    @property
    def active(self) -> dict[str, Entry]:
        return {e.name: e for e in self.entries if not e.trashed}

    @property
    def trash(self) -> list[Entry]:
        return [e for e in self.entries if e.trashed]


async def table_columns(conn: AsyncConnection, table: str) -> set[str] | None:
    def read(sync_conn: Any) -> set[str] | None:
        inspector = inspect(sync_conn)
        if not inspector.has_table(table):
            return None
        return {column["name"] for column in inspector.get_columns(table)}

    return await conn.run_sync(read)


def _plain(value: object) -> object:
    return bytes(value) if isinstance(value, memoryview) else value


async def raw_rows(conn: AsyncConnection, table: str) -> dict[int, dict[str, Any]]:
    """Every row of ``table`` keyed by id, with bytes exactly as stored."""
    if await table_columns(conn, table) is None:
        return {}
    result = await conn.execute(text(f"SELECT * FROM {table} ORDER BY id"))
    return {
        row["id"]: {k: _plain(v) for k, v in row.items()} for row in result.mappings()
    }


async def raw_vault(conn: AsyncConnection) -> dict[str, dict[int, dict[str, Any]]]:
    return {
        table: await raw_rows(conn, table)
        for table in ("master_password", "passwords", "password_attachments")
    }


class _Reader:
    def __init__(self, key: str) -> None:
        self.fernet = Fernet(key)
        self.problems: list[Problem] = []

    def flag(self, table: str, row_id: object, column: str, reason: str) -> None:
        self.problems.append(Problem(table, row_id, column, reason))

    def raw(self, table: str, row_id: object, column: str, token: object) -> bytes:
        return self.raw_or_none(table, row_id, column, token) or b""

    def raw_or_none(
        self, table: str, row_id: object, column: str, token: object
    ) -> bytes | None:
        if not isinstance(token, bytes):
            self.flag(table, row_id, column, "missing or not bytes")
            return None
        try:
            return self.fernet.decrypt(token)
        except InvalidToken:
            self.flag(table, row_id, column, "token does not decrypt")
            return None

    def text(self, table: str, row_id: object, column: str, token: object) -> str:
        data = self.raw(table, row_id, column, token)
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            self.flag(table, row_id, column, "plaintext is not UTF-8")
            return ""

    def optional(
        self, table: str, row_id: object, column: str, token: object
    ) -> str | None:
        return None if token is None else self.text(table, row_id, column, token)

    def json_list(self, row_id: object, column: str, token: object) -> list:
        if token is None:
            return []
        try:
            data = json.loads(self.text("passwords", row_id, column, token) or "[]")
        except json.JSONDecodeError:
            self.flag("passwords", row_id, column, "plaintext is not JSON")
            return []
        if not isinstance(data, list):
            self.flag("passwords", row_id, column, "JSON is not a list")
            return []
        return data

    def tags(self, row_id: object, token: object) -> tuple[str, ...]:
        items = self.json_list(row_id, "tags", token)
        if not all(isinstance(tag, str) for tag in items):
            self.flag("passwords", row_id, "tags", "a tag is not a string")
        return tuple(str(tag) for tag in items)

    def custom_fields(
        self, row_id: object, token: object
    ) -> tuple[tuple[str, str, bool], ...]:
        out: list[tuple[str, str, bool]] = []
        for item in self.json_list(row_id, "custom_fields", token):
            label = item.get("label") if isinstance(item, dict) else None
            value = item.get("value", "") if isinstance(item, dict) else None
            hidden = item.get("hidden", False) if isinstance(item, dict) else None
            if (
                not isinstance(label, str)
                or not isinstance(value, str)
                or not isinstance(hidden, bool)
            ):
                self.flag("passwords", row_id, "custom_fields", "malformed field")
                continue
            out.append((label, value, hidden))
        return tuple(out)

    def history(self, row_id: object, token: object) -> tuple[tuple[str, str], ...]:
        out: list[tuple[str, str]] = []
        for item in self.json_list(row_id, "password_history", token):
            value = item.get("value") if isinstance(item, dict) else None
            changed = item.get("changed_at") if isinstance(item, dict) else None
            if not isinstance(value, str) or not isinstance(changed, str):
                self.flag("passwords", row_id, "password_history", "malformed item")
                continue
            try:
                datetime.fromisoformat(changed)
            except ValueError:
                self.flag("passwords", row_id, "password_history", "bad timestamp")
            out.append((value, changed))
        return tuple(out)


def _check_master(
    reader: _Reader,
    rows: list[dict[str, Any]],
    key: str,
    master_password: str | None,
    require_key_check: bool,
) -> str:
    if not rows:
        reader.flag("master_password", None, "*", "no master password row")
        return "absent"
    if len(rows) > 1:
        reader.flag("master_password", None, "*", f"{len(rows)} rows")
    first = rows[0]
    if master_password is not None and not verify_master_password(
        master_password, first["hash_key"]
    ):
        reader.flag("master_password", first["id"], "hash_key", "password rejected")
    if first.get("key_check") is None:
        if require_key_check:
            reader.flag("master_password", first["id"], "key_check", "absent")
        return "absent"
    if verify_key_check(key, first["key_check"], first["salt"]):
        return "valid"
    reader.flag("master_password", first["id"], "key_check", "does not verify")
    return "invalid"


def _attachments(
    reader: _Reader, rows: dict[int, dict[str, Any]], entry_ids: set[int]
) -> dict[int, list[Attachment]]:
    table = "password_attachments"
    by_entry: dict[int, list[Attachment]] = {}
    for row_id, row in rows.items():
        content = reader.raw_or_none(table, row_id, "content", row["content"])
        if row["password_id"] not in entry_ids:
            reader.flag(table, row_id, "password_id", "no such entry")
        if content is not None and len(content) != row["size_bytes"]:
            reader.flag(table, row_id, "size_bytes", "does not match the content")
        content = content or b""
        by_entry.setdefault(row["password_id"], []).append(
            Attachment(
                id=row_id,
                filename=reader.text(table, row_id, "filename", row["filename"]),
                content_type=reader.optional(
                    table, row_id, "content_type", row["content_type"]
                ),
                size_bytes=row["size_bytes"],
                sha256=hashlib.sha256(content).hexdigest(),
                created=row.get("created"),
            )
        )
    return by_entry


def _entries(
    reader: _Reader,
    rows: dict[int, dict[str, Any]],
    attachments: dict[int, list[Attachment]],
) -> list[Entry]:
    table = "passwords"
    entries = []
    active_names: set[str] = set()
    for row_id, row in rows.items():
        kind = row.get("kind", "login")
        if kind not in KINDS:
            reader.flag(table, row_id, "kind", f"unknown kind {kind!r}")
        if row.get("deleted") is None:
            if row["password_name"] in active_names:
                reader.flag(table, row_id, "password_name", "duplicate active name")
            active_names.add(row["password_name"])
        created, updated = row.get("created"), row.get("updated")
        if created and updated and updated < created:
            reader.flag(table, row_id, "updated", "earlier than created")
        entries.append(
            Entry(
                id=row_id,
                name=row["password_name"],
                kind=kind,
                username=row.get("username"),
                description=row.get("description"),
                value=reader.text(
                    table, row_id, "password_value", row["password_value"]
                ),
                url=reader.optional(table, row_id, "url", row.get("url")),
                totp_secret=reader.optional(
                    table, row_id, "totp_secret", row.get("totp_secret")
                ),
                tags=reader.tags(row_id, row.get("tags")),
                custom_fields=reader.custom_fields(row_id, row.get("custom_fields")),
                folder=reader.optional(table, row_id, "folder", row.get("folder")),
                history=reader.history(row_id, row.get("password_history")),
                favorite=bool(row.get("favorite")),
                backed_up=bool(row.get("backed_up")),
                created=created,
                updated=updated,
                deleted=row.get("deleted"),
                attachments=tuple(attachments.get(row_id, [])),
            )
        )
    return entries


async def read_vault(
    conn: AsyncConnection,
    key: str,
    *,
    master_password: str | None = None,
    known_revisions: Iterable[str] | None = None,
    require_key_check: bool = False,
    strict: bool = True,
) -> VaultContents:
    """
    Decrypt every encrypted column of every entry, active and trashed, and every
    attachment, and check the structural invariants of a v1 vault. Works on any
    schema from v1.0.0 on, reading missing columns as their later defaults.

    Unlike the application's read path nothing is silently replaced: a token
    that does not decrypt, text that is not UTF-8 or JSON of the wrong shape is
    a problem. With ``strict`` any problem raises VaultIntegrityError. A vault
    from before v1.4.6 has no key check; pass ``require_key_check`` for vaults
    that must have one. Columns missing from older schemas read as their later
    defaults, but a NULL where the current schema has a value is a problem.
    """
    reader = _Reader(key)
    raw = await raw_vault(conn)
    key_check = _check_master(
        reader,
        list(raw["master_password"].values()),
        key,
        master_password,
        require_key_check,
    )

    revision = None
    if await table_columns(conn, "alembic_version") is not None:
        revision = await conn.scalar(text("SELECT version_num FROM alembic_version"))
        if known_revisions is not None and revision not in set(known_revisions):
            reader.flag("alembic_version", None, "version_num", f"unknown {revision}")

    attachments = _attachments(
        reader, raw["password_attachments"], set(raw["passwords"])
    )
    entries = _entries(reader, raw["passwords"], attachments)

    settings = tuple(
        {k: v for k, v in row.items() if k not in ("id", "created", "updated")}
        for row in (await raw_rows(conn, "settings")).values()
    )
    if len(settings) > 1:
        reader.flag("settings", None, "*", f"{len(settings)} rows")

    if strict and reader.problems:
        raise VaultIntegrityError(reader.problems)
    return VaultContents(
        revision=revision,
        master_rows=len(raw["master_password"]),
        key_check=key_check,
        entries=tuple(entries),
        settings=settings,
        problems=tuple(reader.problems),
    )


PLAINTEXT_FIELDS = (
    "kind",
    "username",
    "description",
    "value",
    "url",
    "totp_secret",
    "tags",
    "custom_fields",
    "folder",
    "history",
    "favorite",
)


def diff_vaults(
    before: VaultContents,
    after: VaultContents,
    *,
    compare: Iterable[str] = PLAINTEXT_FIELDS,
    attachments: bool = True,
    trash: bool = True,
) -> list[str]:
    """
    Every difference between two vaults' decrypted contents as readable lines.
    Entries are matched by (trashed, name, deleted time), never by row id, so
    the comparison also works after a restore into a fresh database.
    """
    names = list(compare)
    unknown = set(names) - {f.name for f in fields(Entry)}
    if unknown:
        raise ValueError(f"unknown entry fields: {sorted(unknown)}")

    def index(vault: VaultContents) -> dict[tuple, Entry]:
        return {
            (e.trashed, e.name, e.deleted): e
            for e in vault.entries
            if trash or not e.trashed
        }

    left, right = index(before), index(after)
    out = [f"missing after: {key}" for key in left.keys() - right.keys()]
    out += [f"new after: {key}" for key in right.keys() - left.keys()]
    for key in left.keys() & right.keys():
        a, b = left[key], right[key]
        for name in names:
            if getattr(a, name) != getattr(b, name):
                out.append(
                    f"{key} {name}: {getattr(a, name)!r} != {getattr(b, name)!r}"
                )
        if attachments:
            mine = sorted(x.identity for x in a.attachments)
            theirs = sorted(x.identity for x in b.attachments)
            if mine != theirs:
                out.append(f"{key} attachments: {mine!r} != {theirs!r}")
    return sorted(out)


def assert_same_vault(
    before: VaultContents, after: VaultContents, **options: Any
) -> None:
    differences = diff_vaults(before, after, **options)
    assert not differences, "vault contents differ:\n" + "\n".join(differences)


def diff_ciphertext(
    before: Mapping[str, Mapping[int, Mapping[str, Any]]],
    after: Mapping[str, Mapping[int, Mapping[str, Any]]],
    columns: Mapping[str, Iterable[str]] = ENCRYPTED_COLUMNS,
) -> list[str]:
    """Byte-level differences in the encrypted columns of rows from raw_vault."""
    out = []
    for table, names in columns.items():
        a, b = before.get(table, {}), after.get(table, {})
        if a.keys() != b.keys():
            out.append(f"{table}: row ids {sorted(a)} != {sorted(b)}")
        for row_id in sorted(a.keys() & b.keys()):
            for name in names:
                if a[row_id].get(name) != b[row_id].get(name):
                    out.append(f"{table}[{row_id}].{name} changed")
    return out
