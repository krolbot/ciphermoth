import hashlib
import json
import tempfile
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import IO, Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    field_validator,
)
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backup_format import (
    FRAME_OVERHEAD,
    MAX_BACKUP_BYTES,
    MAX_MANIFEST_BYTES,
    BackupReader,
    BackupWriter,
)
from crud.attachment import (
    MAX_ATTACHMENT_BYTES,
    MAX_ATTACHMENTS_PER_ENTRY,
    MAX_TOTAL_BYTES,
)
from crud.master_password import MasterPasswordCRUD
from crud.password import (
    SOURCE_KEYS,
    Ignored,
    Imported,
    PasswordCRUD,
    document_from,
    normalize_custom_fields,
)
from crud.records import (
    AttachmentMetadata,
    EntryDocument,
    HistoryItem,
    history_timestamp,
    open_attachment_content,
    open_attachment_metadata,
    open_entry,
    seal_attachment,
    seal_entry,
)
from crud.settings import SettingsCRUD
from errors import Forbidden, InvalidRequest
from helpers import (
    BACKUP_HEADER_BYTES,
    DEFAULT_KDF,
    BackupFormatError,
    BackupHeader,
    BackupKey,
    DecryptionFailed,
    VaultKey,
    backup_key_for,
    new_backup_key,
    read_legacy_backup,
)
from models import AttachmentModel, EntryModel
from schemas import (
    OnConflict,
    PasswordImportResult,
    RestoredPassword,
    SettingsUpdate,
)
from settings import get_api_settings
from validators import require_unicode_text
from vault_sessions import VaultSessions

MAX_LEGACY_FILE_BYTES = 10 * 1024 * 1024
MAX_LEGACY_JSON_BYTES = 50 * 1024 * 1024
_SPOOL_BYTES = 16 * 1024 * 1024
_LEGACY_MAGIC = b"PK\x03\x04"

_WRONG_PASSWORD = (
    "Incorrect backup password. Use the master password the vault had when the "
    "backup was made."
)
_DAMAGED = "The backup file is damaged or incomplete. Nothing was imported."


def _utc(value: datetime) -> datetime:
    """Naive UTC, as the vault stores times. A time whose offset pushes it out
    of the representable range is refused as invalid input."""
    if value.tzinfo is None:
        return value
    try:
        return value.astimezone(UTC).replace(tzinfo=None)
    except OverflowError:
        raise ValueError("is out of range once converted to UTC") from None


def _stamp(value: datetime) -> str:
    return value.replace(tzinfo=UTC).isoformat()


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    @field_validator("*")
    @classmethod
    def _unicode(cls, value: object) -> object:
        return require_unicode_text(value)


class BackupAttachment(_Strict):
    filename: str
    content_type: str | None
    size: int = Field(ge=1, le=MAX_ATTACHMENT_BYTES)
    sha256: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
    created: datetime

    @field_validator("created")
    @classmethod
    def _in_utc(cls, value: datetime) -> datetime:
        return _utc(value)


class BackupHistoryItem(_Strict):
    value: str
    changed_at: str

    @field_validator("changed_at")
    @classmethod
    def _timestamp(cls, value: str) -> str:
        return history_timestamp(value)


class BackupField(_Strict):
    label: str
    value: str
    hidden: bool


class BackupEntry(_Strict):
    name: str
    kind: Literal["login", "note"]
    username: str | None
    value: str
    url: str | None
    totp_secret: str | None
    description: str | None
    tags: list[str]
    custom_fields: list[BackupField]
    folder: str | None
    favorite: bool
    history: list[BackupHistoryItem]
    created: datetime
    updated: datetime
    deleted: datetime | None

    @field_validator("created", "updated", "deleted")
    @classmethod
    def _in_utc(cls, value: datetime | None) -> datetime | None:
        return None if value is None else _utc(value)

    attachments: list[BackupAttachment] = Field(max_length=MAX_ATTACHMENTS_PER_ENTRY)

    @field_validator("tags")
    @classmethod
    def _unicode_tags(cls, value: list[str]) -> list[str]:
        require_unicode_text(value)
        return value


class BackupSettings(_Strict):
    inactivity_ms: int
    warn_before_ms: int
    hidden_ms: int
    debounce_ms: int
    clipboard_clear_ms: int
    update_check_enabled: bool


class BackupManifest(_Strict):
    format: Literal["ciphermoth-backup"]
    version: Literal[2]
    exported_at: datetime

    @field_validator("exported_at")
    @classmethod
    def _in_utc(cls, value: datetime) -> datetime:
        return _utc(value)

    app_version: str
    settings: BackupSettings
    entries: list[BackupEntry]


class BackupCRUD(PasswordCRUD):
    def __init__(self, session: AsyncSession, vault_sessions: VaultSessions) -> None:
        super().__init__(session)
        self.vault_sessions = vault_sessions
        self.master_password = MasterPasswordCRUD(session)

    async def _settings(self) -> BackupSettings:
        current = await SettingsCRUD(self.session, self.vault_sessions).get_settings()
        return BackupSettings(**current.model_dump())

    async def _attachments_of(
        self, key: VaultKey, entry: EntryModel
    ) -> list[tuple[int, BackupAttachment]]:
        ids = (
            await self.session.scalars(
                select(AttachmentModel.id)
                .where(AttachmentModel.entry_id == entry.id)
                .order_by(AttachmentModel.id)
            )
        ).all()
        described = []
        for attachment_id in ids:
            content, metadata, created = await self._attachment(
                key, entry, attachment_id
            )
            described.append(
                (
                    attachment_id,
                    BackupAttachment(
                        filename=metadata.filename,
                        content_type=metadata.content_type,
                        size=len(content),
                        sha256=hashlib.sha256(content).hexdigest(),
                        created=created,
                    ),
                )
            )
        return described

    async def _attachment(
        self, key: VaultKey, entry: EntryModel, attachment_id: int
    ) -> tuple[bytes, AttachmentMetadata, datetime]:
        attachment = await self.session.get_one(AttachmentModel, attachment_id)
        metadata = open_attachment_metadata(key, attachment, entry.uid)
        content = open_attachment_content(key, attachment, entry.uid)
        created = attachment.created
        self.session.expunge(attachment)
        return content, metadata, created

    async def create_backup(self, master_password: str, key: VaultKey) -> IO[bytes]:
        """
        A complete backup of the vault (backup format 2) in a temporary file
        that holds only ciphertext. Both KDFs (checking the master password and
        deriving the backup key from a new salt) run before the write lock is
        taken; the vault is then read in one transaction, which also marks
        every entry as backed up.
        """
        opened = await self.master_password.check_master_password(master_password)
        salt, backup_key = await new_backup_key(master_password)
        await self.master_password.confirm_same_key(opened, key)

        entries = list(
            await self.session.scalars(select(EntryModel).order_by(EntryModel.id))
        )
        manifest_entries = []
        frames: list[tuple[EntryModel, int, BackupAttachment]] = []
        for entry in entries:
            document = open_entry(key, entry)
            attachments = await self._attachments_of(key, entry)
            frames += [(entry, i, described) for i, described in attachments]
            manifest_entries.append(
                {
                    **document.model_dump(),
                    "created": _stamp(entry.created),
                    "updated": _stamp(entry.updated),
                    "deleted": _stamp(entry.deleted) if entry.deleted else None,
                    "attachments": [
                        {
                            **described.model_dump(),
                            "created": _stamp(described.created),
                        }
                        for _, described in attachments
                    ],
                }
            )
        manifest = {
            "format": "ciphermoth-backup",
            "version": 2,
            "exported_at": _stamp(datetime.now(UTC).replace(tzinfo=None)),
            "app_version": get_api_settings().version,
            "settings": (await self._settings()).model_dump(),
            "entries": manifest_entries,
        }

        encoded = json.dumps(manifest, ensure_ascii=False).encode()
        self._check_restorable(encoded, [described.size for _, _, described in frames])
        header = BackupHeader(
            params=DEFAULT_KDF,
            salt=salt,
            frames=1 + len(frames),
            commitment=backup_key.commitment,
        )
        target = tempfile.SpooledTemporaryFile(max_size=_SPOOL_BYTES)
        try:
            writer = BackupWriter(target, backup_key, header)
            writer.write(encoded)
            for entry, attachment_id, described in frames:
                content, _, _ = await self._attachment(key, entry, attachment_id)
                if hashlib.sha256(content).hexdigest() != described.sha256:
                    raise InvalidRequest("An attachment changed while backing up.")
                writer.write(content)
            writer.finish()
        except BaseException:
            target.close()
            raise

        await self.session.execute(
            update(EntryModel)
            .values(backed_up=True, updated=EntryModel.updated)
            .execution_options(synchronize_session=False)
        )
        target.seek(0)
        return target

    @staticmethod
    def _check_restorable(manifest: bytes, attachment_sizes: list[int]) -> None:
        """Refuse to write a backup this release could not restore, instead of
        reporting success for a file every import would reject."""
        if len(manifest) > MAX_MANIFEST_BYTES:
            raise InvalidRequest(
                "The vault's entries are too large for one backup (over 64 MB of "
                "text, history included). Nothing was written."
            )
        total = BACKUP_HEADER_BYTES + sum(
            FRAME_OVERHEAD + size for size in [len(manifest), *attachment_sizes]
        )
        if total > MAX_BACKUP_BYTES:
            raise InvalidRequest(
                "The vault is too large for one backup (over 1 GB with its "
                "attachments). Nothing was written."
            )

    async def import_backup(
        self,
        upload: IO[bytes],
        password: str,
        key: VaultKey,
        on_conflict: OnConflict,
    ) -> PasswordImportResult:
        """
        Restore a backup file into the vault: a complete backup (format 2) or a
        backup ZIP from CipherMoth 2.0 or earlier. Everything is checked before
        the import's single write transaction commits, so a wrong password, a
        damaged, truncated or inconsistent file changes nothing.
        """
        start = upload.read(len(_LEGACY_MAGIC))
        upload.seek(0)
        if start == _LEGACY_MAGIC:
            return await self._import_legacy(upload, password, key, on_conflict)
        try:
            reader = BackupReader(upload)
        except BackupFormatError as error:
            raise InvalidRequest(str(error)) from None
        await self.session.commit()

        backup_key = await backup_key_for(password, reader.header)
        if not backup_key.matches(reader.header):
            raise Forbidden(_WRONG_PASSWORD)
        try:
            manifest = BackupManifest.model_validate_json(
                reader.read(backup_key, MAX_MANIFEST_BYTES), strict=True
            )
        except (BackupFormatError, DecryptionFailed):
            raise InvalidRequest(_DAMAGED) from None
        except ValidationError as error:
            raise InvalidRequest(self._manifest_problem(error)) from None
        restored = self._check_manifest(manifest, reader.remaining)

        await self.master_password.verify_vault_key(key)
        try:
            return await self._restore(
                reader, backup_key, manifest, restored, key, on_conflict
            )
        except (BackupFormatError, DecryptionFailed):
            raise InvalidRequest(_DAMAGED) from None

    @staticmethod
    def _manifest_problem(error: ValidationError) -> str:
        problem = error.errors()[0]
        location = problem["loc"]
        where = "the backup"
        if len(location) >= 2 and location[0] == "entries":
            where = f"entry {int(location[1]) + 1}"
        field = ".".join(str(part) for part in location[2:]) or "content"
        return f"Nothing was imported. {where} ({field}): {problem['msg']}."

    def _check_manifest(
        self, manifest: BackupManifest, attachment_frames: int
    ) -> list[tuple[Imported, list[HistoryItem]]]:
        restored, ignored = self.validate_import(
            (
                (f"entry {index}", self._restorable(entry))
                for index, entry in enumerate(manifest.entries, start=1)
            ),
            label_for=lambda field: SOURCE_KEYS.get(field, field),
            schema=RestoredPassword,
        )
        if ignored:
            raise InvalidRequest(
                f"Nothing was imported. {ignored[0].where}: {ignored[0].reason}."
            )
        active: dict[str, int] = {}
        for index, entry in enumerate(manifest.entries, start=1):
            if sum(a.size for a in entry.attachments) > MAX_TOTAL_BYTES:
                raise InvalidRequest(
                    f"Nothing was imported. entry {index}: its attachments exceed "
                    "the 25 MB limit."
                )
            if entry.deleted is None:
                if entry.name in active:
                    raise InvalidRequest(
                        f"Nothing was imported. entry {index} has the same name as "
                        f"entry {active[entry.name]}; a vault cannot hold both."
                    )
                active[entry.name] = index
        if sum(len(e.attachments) for e in manifest.entries) != attachment_frames:
            raise InvalidRequest(_DAMAGED)
        try:
            SettingsUpdate(**manifest.settings.model_dump())
        except ValidationError:
            raise InvalidRequest(
                "Nothing was imported. The backup's settings are invalid."
            ) from None
        return [
            (
                password,
                [
                    HistoryItem(value=item.value, changed_at=item.changed_at)
                    for item in entry.history
                ],
            )
            for (_, password), entry in zip(restored, manifest.entries, strict=True)
        ]

    @staticmethod
    def _restorable(entry: BackupEntry) -> dict[str, object] | Ignored:
        if not entry.name:
            return Ignored(None, "no name")
        if not entry.value:
            return Ignored(entry.name, "no password or note text")
        return {
            "password_name": entry.name,
            "password_value": entry.value,
            "kind": entry.kind,
            "username": entry.username,
            "url": entry.url,
            "totp_secret": entry.totp_secret,
            "description": entry.description,
            "tags": entry.tags,
            "custom_fields": [field.model_dump() for field in entry.custom_fields],
            "folder": entry.folder,
            "favorite": entry.favorite,
        }

    async def _restore(
        self,
        reader: BackupReader,
        backup_key: BackupKey,
        manifest: BackupManifest,
        restored: list[tuple[Imported, list[HistoryItem]]],
        key: VaultKey,
        on_conflict: OnConflict,
    ) -> PasswordImportResult:
        vault_was_empty = not await self.session.scalar(
            select(func.count()).select_from(EntryModel)
        )
        active = await self.load_active()
        trashed = {
            (bytes(index), deleted)
            for index, deleted in (
                await self.session.execute(
                    select(EntryModel.name_index, EntryModel.deleted).where(
                        EntryModel.deleted.is_not(None)
                    )
                )
            ).all()
        }
        counts = {"imported": 0, "skipped": 0, "overwritten": 0, "trashed": 0}
        attachments = 0
        moved_at = datetime.now(UTC).replace(tzinfo=None)
        for entry, (password, history) in zip(manifest.entries, restored, strict=True):
            document = document_from(password, history)
            target = await self._restore_target(
                document, entry, active, trashed, key, on_conflict, moved_at, counts
            )
            for described in entry.attachments:
                content = reader.read(backup_key, MAX_ATTACHMENT_BYTES)
                if (
                    len(content) != described.size
                    or hashlib.sha256(content).hexdigest() != described.sha256
                ):
                    raise InvalidRequest(_DAMAGED)
                if target is None:
                    continue
                attachment = AttachmentModel(
                    entry_id=target.id, created=described.created
                )
                seal_attachment(
                    key,
                    attachment,
                    target.uid,
                    AttachmentMetadata(
                        filename=described.filename,
                        content_type=described.content_type,
                    ),
                    content,
                )
                self.session.add(attachment)
                await self.session.flush()
                self.session.expunge(attachment)
                attachments += 1
        reader.finish()

        settings_restored = vault_was_empty and bool(manifest.entries)
        if settings_restored:
            await SettingsCRUD(self.session, self.vault_sessions).update_settings(
                SettingsUpdate(**manifest.settings.model_dump())
            )
        summary = self.result(
            {name: counts[name] for name in ("imported", "skipped", "overwritten")},
            [],
            [],
        )
        return summary.model_copy(
            update={
                "total": len(manifest.entries),
                "trashed": counts["trashed"],
                "attachments": attachments,
                "settings_restored": settings_restored,
            }
        )

    async def _restore_target(
        self,
        document: EntryDocument,
        entry: BackupEntry,
        active: dict[bytes, EntryModel],
        trashed: set[tuple[bytes, datetime]],
        key: VaultKey,
        on_conflict: OnConflict,
        moved_at: datetime,
        counts: dict[str, int],
    ) -> EntryModel | None:
        index = key.name_index(document.name)
        deleted = entry.deleted
        if deleted is not None:
            if (index, deleted) in trashed:
                counts["skipped"] += 1
                return None
            trashed.add((index, deleted))
            counts["trashed"] += 1
        else:
            existing = active.get(index)
            if existing is not None:
                if on_conflict == OnConflict.skip:
                    counts["skipped"] += 1
                    return None
                existing.deleted = moved_at
                await self.session.flush()
                counts["overwritten"] += 1
            else:
                counts["imported"] += 1
        model = EntryModel(
            created=entry.created,
            updated=entry.updated,
            deleted=deleted,
            backed_up=True,
        )
        seal_entry(key, model, document)
        self.session.add(model)
        await self.session.flush()
        if deleted is None:
            active[index] = model
        return model

    async def _import_legacy(
        self,
        upload: IO[bytes],
        password: str,
        key: VaultKey,
        on_conflict: OnConflict,
    ) -> PasswordImportResult:
        data = upload.read(MAX_LEGACY_FILE_BYTES + 1)
        if len(data) > MAX_LEGACY_FILE_BYTES:
            raise InvalidRequest(
                "Backup ZIP files larger than 10 MB are not supported."
            )
        await self.session.commit()
        try:
            raw = read_legacy_backup(data, password, MAX_LEGACY_JSON_BYTES)
        except DecryptionFailed:
            raise Forbidden(_WRONG_PASSWORD) from None
        except BackupFormatError as error:
            raise InvalidRequest(
                f"{error} Ensure it is a valid CipherMoth backup."
            ) from None
        try:
            entries = json.loads(raw)["passwords"]
            if not isinstance(entries, list):
                raise ValueError
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            raise InvalidRequest("Invalid backup file format.") from e

        passwords, ignored = self.validate_import(
            self._legacy_rows(entries),
            label_for=lambda field: SOURCE_KEYS.get(field, field),
            schema=RestoredPassword,
        )
        await self.master_password.verify_vault_key(key)
        return await self._store_import(passwords, ignored, key, on_conflict)

    @classmethod
    def _legacy_rows(
        cls, entries: Iterable[object]
    ) -> Iterable[tuple[str, dict[str, object] | Ignored]]:
        for index, item in enumerate(entries, start=1):
            yield f"entry {index}", cls._legacy_fields(item)

    @staticmethod
    def _legacy_tags(raw: object) -> object:
        if not isinstance(raw, list):
            return raw or []
        return [str(tag) for tag in raw if tag is not None]

    @classmethod
    def _legacy_fields(cls, item: object) -> dict[str, object] | Ignored:
        if not isinstance(item, dict):
            return Ignored(None, "not an entry")
        name, value = item.get("name"), item.get("value")
        if not name or (isinstance(name, str) and not name.strip()):
            return Ignored(None, "no name")
        if not value:
            return Ignored(name, "no password or note text")
        return {
            "password_name": name,
            "password_value": value,
            "kind": "note" if item.get("kind") == "note" else "login",
            "username": item.get("username"),
            "url": item.get("url"),
            "totp_secret": item.get("totp_secret"),
            "description": item.get("description"),
            "tags": cls._legacy_tags(item.get("tags")),
            "custom_fields": normalize_custom_fields(item.get("custom_fields")),
            "folder": item.get("folder"),
            "favorite": bool(item.get("favorite", False)),
        }
