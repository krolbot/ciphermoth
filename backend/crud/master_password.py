import logging
import os
from typing import Literal

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from crud.base import BaseCRUD
from errors import Forbidden, InvalidKey, InvalidRequest, NotFound
from helpers import (
    create_key_check,
    decrypt,
    decrypt_bytes,
    derive_key,
    encrypt,
    hash_password,
    password_matches,
    verify_key_check,
)
from models import MasterPasswordModel, PasswordAttachmentModel, PasswordModel
from schemas import MasterPasswordUpdate

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
            raise InvalidRequest(f"Could not decrypt password '{pwd.password_name}'.")
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
            raise InvalidRequest("Could not decrypt an attachment.")
        return encrypt(new_key, plaintext.encode())

    @staticmethod
    def _reencrypt_binary(
        old_key: bytes | str, new_key: bytes | str, token: bytes
    ) -> bytes:
        raw = decrypt_bytes(old_key, token)
        if raw is None:
            raise InvalidRequest("Could not decrypt an attachment.")
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
        that arrives during it re-checks against the new key afterwards. The key is
        checked once before locking so requests with a wrong key never take a lock.
        """
        if not key_derivation:
            raise InvalidKey("Key derivation is missing.")
        model = await fetch_master_password(self.session)
        if model is None:
            raise Forbidden("No master password set.")
        if not verify_key_check(key_derivation, model.key_check, model.salt):
            raise InvalidKey(_INVALID_KEY)
        model = await fetch_master_password(
            self.session, lock="update" if exclusive else "share"
        )
        if model is None or not verify_key_check(
            key_derivation, model.key_check, model.salt
        ):
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
            .values(key_check=create_key_check(key_derivation, observed.salt))
            .returning(MasterPasswordModel.id)
            .execution_options(synchronize_session=False)
        )
        return stored.scalar() is not None

    async def unlock(self, master_password: str) -> str | None:
        """
        Return the vault key for ``master_password``, or None if it is wrong.

        A verified password (re)writes a missing or stale key check. The result is
        confirmed under the shared vault row lock, so a password that a concurrent
        master password change has just replaced is refused, not turned into a key
        that every route would reject. The read-only transaction is ended before
        the slow KDFs so a queue of unlocks holds no database connections.
        """
        model = await self._get_model()
        await self.session.commit()
        if not await password_matches(master_password, model.hash_key):
            return None
        key = (await derive_key(model.salt, master_password)).decode()
        if not verify_key_check(key, model.key_check, model.salt):
            if model.key_check is not None:
                logger.warning(
                    "Stored vault key check did not match the verified master "
                    "password; replacing it."
                )
            await self.store_key_check(model, key)
        current = await fetch_master_password(self.session, lock="share")
        if current is None or not verify_key_check(
            key, current.key_check, current.salt
        ):
            return None
        return key

    async def create_master_password(self, master_password: str) -> str:
        if await self.is_initialized():
            raise Forbidden("Master password already exists.")
        await self.session.commit()
        salt = os.urandom(16)
        key_derivation = await derive_key(salt, master_password)
        hash_key = await hash_password(master_password)

        await self.session.execute(
            text("LOCK TABLE master_password IN SHARE ROW EXCLUSIVE MODE")
        )
        if await self.is_initialized():
            raise Forbidden("Master password already exists.")

        self.session.add(
            MasterPasswordModel(
                salt=salt,
                hash_key=hash_key,
                key_check=create_key_check(key_derivation, salt),
            )
        )
        await self.session.flush()
        return key_derivation.decode()

    async def update_master_password(
        self, master_password: str, new_master_password: str
    ) -> MasterPasswordUpdate:
        model = await self._get_model(lock="update")
        if not await password_matches(master_password, model.hash_key):
            raise Forbidden("Current master password is incorrect.")

        key_derivation = await derive_key(model.salt, master_password)
        if not verify_key_check(key_derivation, model.key_check, model.salt):
            raise InvalidKey(_INVALID_KEY)

        new_salt = os.urandom(16)
        new_key_derivation = await derive_key(new_salt, new_master_password)
        new_hash_key = await hash_password(new_master_password)

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
        model.hash_key = new_hash_key
        model.key_check = create_key_check(new_key_derivation, new_salt)
        self.session.add(model)
        await self.session.flush()

        return MasterPasswordUpdate(
            updated=True, detail="Master password updated successfully."
        )
