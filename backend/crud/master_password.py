import logging
import os
from typing import Literal

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from api.exceptions import Forbidden, InvalidKey, NotFound, TypesMismatchError
from crud.base import BaseCRUD
from helpers import (
    create_key_check,
    decrypt,
    decrypt_bytes,
    encrypt,
    generate_key_derivation,
    hash_master_password,
    verify_key_check,
    verify_master_password,
)
from models import MasterPasswordModel, PasswordAttachmentModel, PasswordModel
from schemas import (
    MasterPasswordCheck,
    MasterPasswordCreate,
    MasterPasswordUpdate,
)

logger = logging.getLogger(__name__)

_INVALID_KEY = "Invalid or expired vault key. Unlock the vault again."


async def fetch_master_password(
    session: AsyncSession, *, lock: Literal["share", "update"] | None = None
) -> MasterPasswordModel | None:
    stmt = select(MasterPasswordModel).order_by(MasterPasswordModel.id).limit(1)
    if lock is not None:
        stmt = stmt.with_for_update(read=lock == "share").execution_options(
            populate_existing=True
        )
    return (await session.execute(stmt)).scalar()


class MasterPasswordCRUD(BaseCRUD):
    _OPTIONAL_ENCRYPTED_FIELDS = (
        "url",
        "totp_secret",
        "tags",
        "custom_fields",
        "folder",
        "password_history",
    )

    @staticmethod
    def _reencrypt(
        old_key: bytes | str, new_key: bytes | str, token: bytes, pwd: PasswordModel
    ) -> bytes:
        plaintext = decrypt(old_key, token)
        if plaintext is None:
            raise TypesMismatchError(
                f"Could not decrypt password '{pwd.password_name}'."
            )
        return encrypt(new_key, plaintext.encode())

    @classmethod
    def _reencrypt_optional(
        cls,
        old_key: bytes | str,
        new_key: bytes | str,
        token: bytes | None,
        pwd: PasswordModel,
    ) -> bytes | None:
        if token is None:
            return None
        return cls._reencrypt(old_key, new_key, token, pwd)

    @staticmethod
    def _reencrypt_text(
        old_key: bytes | str, new_key: bytes | str, token: bytes | None
    ) -> bytes | None:
        if token is None:
            return None
        plaintext = decrypt(old_key, token)
        if plaintext is None:
            raise TypesMismatchError("Could not decrypt an attachment.")
        return encrypt(new_key, plaintext.encode())

    @staticmethod
    def _reencrypt_binary(
        old_key: bytes | str, new_key: bytes | str, token: bytes
    ) -> bytes:
        raw = decrypt_bytes(old_key, token)
        if raw is None:
            raise TypesMismatchError("Could not decrypt an attachment.")
        return encrypt(new_key, raw)

    async def is_initialized(self) -> bool:
        return await fetch_master_password(self.session) is not None

    async def _get_model(
        self, lock: Literal["share", "update"] | None = None
    ) -> MasterPasswordModel:
        model = await fetch_master_password(self.session, lock=lock)
        if not model:
            raise NotFound("No master password found.")
        return model

    async def verify_vault_key(
        self, key_derivation: str | None, *, exclusive: bool = False
    ) -> str:
        """
        Check that ``key_derivation`` is the current vault key and lock the vault
        row for the rest of the request's transaction.

        The shared lock keeps a master password change from committing while a
        request that was checked against the old key is still writing; a change
        takes the exclusive lock, so it waits for those requests and any request
        that arrives during it re-checks against the new key afterwards.
        """
        if not key_derivation:
            raise InvalidKey("Key derivation is missing.")
        model = await fetch_master_password(
            self.session, lock="update" if exclusive else "share"
        )
        if model is None:
            raise Forbidden("No master password set.")
        if not verify_key_check(key_derivation, model.key_check):
            raise InvalidKey(_INVALID_KEY)
        return key_derivation

    async def store_key_check(
        self, observed: MasterPasswordModel, key_derivation: bytes | str
    ) -> bool:
        """
        Write a key check for ``key_derivation`` only if the row still holds the
        salt, hash and key check that were read, so an unlock that raced a master
        password change can never overwrite the newer key check.
        """
        unchanged = (
            MasterPasswordModel.key_check.is_(None)
            if observed.key_check is None
            else MasterPasswordModel.key_check == observed.key_check
        )
        stored = await self.session.execute(
            update(MasterPasswordModel)
            .where(
                MasterPasswordModel.id == observed.id,
                MasterPasswordModel.salt == observed.salt,
                MasterPasswordModel.hash_key == observed.hash_key,
                unchanged,
            )
            .values(key_check=create_key_check(key_derivation))
            .returning(MasterPasswordModel.id)
            .execution_options(synchronize_session=False)
        )
        return stored.scalar() is not None

    async def check_master_password(self, master_password: str) -> MasterPasswordCheck:
        model = await self._get_model()
        if not verify_master_password(master_password, model.hash_key):
            return MasterPasswordCheck(valid=False)
        key_derivation = generate_key_derivation(model.salt, master_password)
        if not verify_key_check(key_derivation, model.key_check):
            if model.key_check is not None:
                logger.warning(
                    "Stored vault key check did not match the verified master "
                    "password; replacing it."
                )
            await self.store_key_check(model, key_derivation)
        return MasterPasswordCheck(valid=True, key_derivation=key_derivation.decode())

    async def create_master_password(
        self, master_password: str
    ) -> MasterPasswordCreate:
        if await self.is_initialized():
            raise Forbidden("Master password already exists.")
        salt = os.urandom(16)
        key_derivation = generate_key_derivation(salt, master_password)
        hash_key = hash_master_password(master_password)

        await self.session.execute(
            text("LOCK TABLE master_password IN SHARE ROW EXCLUSIVE MODE")
        )
        if await self.is_initialized():
            raise Forbidden("Master password already exists.")

        self.session.add(
            MasterPasswordModel(
                salt=salt,
                hash_key=hash_key,
                key_check=create_key_check(key_derivation),
            )
        )
        await self.session.flush()
        return MasterPasswordCreate(
            created=True,
            detail="Master password created successfully.",
            key_derivation=key_derivation.decode(),
        )

    async def update_master_password(
        self, master_password: str, new_master_password: str
    ) -> MasterPasswordUpdate:
        model = await self._get_model(lock="update")
        if not verify_master_password(master_password, model.hash_key):
            raise Forbidden("Current master password is incorrect.")

        key_derivation = generate_key_derivation(model.salt, master_password)
        if not verify_key_check(key_derivation, model.key_check):
            raise InvalidKey(_INVALID_KEY)

        new_salt = os.urandom(16)
        new_key_derivation = generate_key_derivation(new_salt, new_master_password)

        passwords = (
            await self.session.execute(
                select(PasswordModel).order_by(PasswordModel.password_name)
            )
        ).scalars()

        for pwd in passwords:
            pwd.password_value = self._reencrypt(
                key_derivation, new_key_derivation, pwd.password_value, pwd
            )
            for field in self._OPTIONAL_ENCRYPTED_FIELDS:
                setattr(
                    pwd,
                    field,
                    self._reencrypt_optional(
                        key_derivation, new_key_derivation, getattr(pwd, field), pwd
                    ),
                )

        attachments = (
            await self.session.execute(select(PasswordAttachmentModel))
        ).scalars()
        for att in attachments:
            att.filename = self._reencrypt_binary(
                key_derivation, new_key_derivation, att.filename
            )
            att.content = self._reencrypt_binary(
                key_derivation, new_key_derivation, att.content
            )
            att.content_type = self._reencrypt_text(
                key_derivation, new_key_derivation, att.content_type
            )

        model.salt = new_salt
        model.hash_key = hash_master_password(new_master_password)
        model.key_check = create_key_check(new_key_derivation)
        self.session.add(model)
        await self.session.flush()

        return MasterPasswordUpdate(
            updated=True, detail="Master password updated successfully."
        )
