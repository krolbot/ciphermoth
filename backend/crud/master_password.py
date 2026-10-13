import logging
import os

from sqlalchemy import select
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


_DAMAGED = (
    "The vault's key check does not match its master password. The vault file may "
    "be damaged; restore a snapshot (docs/UPDATING.md)."
)


async def fetch_master_password(session: AsyncSession) -> MasterPasswordModel | None:
    stmt = (
        select(MasterPasswordModel)
        .order_by(MasterPasswordModel.id)
        .limit(1)
        .execution_options(populate_existing=True)
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

    async def _get_model(self) -> MasterPasswordModel:
        model = await fetch_master_password(self.session)
        if not model:
            raise NotFound("No master password found.")
        return model

    async def verify_vault_key(self, key_derivation: str | None) -> str:
        """
        Check that ``key_derivation`` is the current vault key, inside the
        request's transaction. Write requests run under SQLite's write lock from
        their first statement (BEGIN IMMEDIATE), so a master password change can
        never commit between this check and their writes; read requests see the
        key check and the rows of one snapshot.
        """
        if not key_derivation:
            raise InvalidKey("Key derivation is missing.")
        model = await fetch_master_password(self.session)
        if model is None:
            raise Forbidden("No master password set.")
        if not verify_key_check(key_derivation, model.key_check, model.salt):
            raise InvalidKey(_INVALID_KEY)
        return key_derivation

    async def unlock(self, master_password: str) -> str | None:
        """
        Return the vault key for ``master_password``, or None if it is wrong.

        The transaction is ended before the slow KDFs so a queue of unlocks holds
        no connection and no lock. The key is then confirmed against the current
        key check, so a password that a concurrent change has just replaced is
        refused instead of opening a session every route would reject.
        """
        model = await self._get_model()
        await self.session.commit()
        if not await password_matches(master_password, model.hash_key):
            return None
        key = (await derive_key(model.salt, master_password)).decode()
        if not verify_key_check(key, model.key_check, model.salt):
            logger.error("The vault key check does not match the verified password.")
            raise InvalidRequest(_DAMAGED)
        current = await fetch_master_password(self.session)
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
        """
        Re-encrypt every entry and attachment under a key derived from the new
        password and a new salt. The KDFs run before the write lock is taken; the
        re-encryption then runs in one write transaction that first confirms the
        vault still holds the salt, hash and key check the KDFs were based on.
        """
        model = await self._get_model()
        observed = (model.salt, model.hash_key, model.key_check)
        await self.session.commit()
        if not await password_matches(master_password, model.hash_key):
            raise Forbidden("Current master password is incorrect.")

        key_derivation = await derive_key(model.salt, master_password)
        if not verify_key_check(key_derivation, model.key_check, model.salt):
            raise InvalidKey(_INVALID_KEY)

        new_salt = os.urandom(16)
        new_key_derivation = await derive_key(new_salt, new_master_password)
        new_hash_key = await hash_password(new_master_password)

        model = await self._get_model()
        if (model.salt, model.hash_key, model.key_check) != observed:
            raise InvalidKey(_INVALID_KEY)

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
