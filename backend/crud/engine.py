import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import URL, Connection, event
from sqlalchemy.exc import DatabaseError, DBAPIError, OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeout
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from errors import VaultBusy
from settings import get_storage_settings
from storage import (
    StorageError,
    configure_connection,
    ensure_schema,
    prepare_data_dir,
    require_supported_sqlite,
    vault_file,
)

_AFTER_COMMIT = "ciphermoth_after_commit"
_AFTER_ROLLBACK = "ciphermoth_after_rollback"
_BEGIN = "ciphermoth_begin"
_BUSY_CODES = frozenset({5, 6})
_BUSY_DETAIL = "The vault is busy with another change. Try again in a moment."


def _connect(dbapi_connection: object, _record: object) -> None:
    configure_connection(dbapi_connection)


def _begin(connection: Connection) -> None:
    mode = connection.get_execution_options().get(_BEGIN, "DEFERRED")
    connection.exec_driver_sql(f"BEGIN {mode}")


def create_engine(path: Path, **pool: Any) -> AsyncEngine:
    require_supported_sqlite()
    engine = create_async_engine(
        URL.create("sqlite+aiosqlite", database=str(path)), **pool
    )
    event.listen(engine.sync_engine, "connect", _connect)
    event.listen(engine.sync_engine, "begin", _begin)
    return engine


def is_busy(error: OperationalError) -> bool:
    code = getattr(error.orig, "sqlite_errorcode", None)
    return isinstance(code, int) and code & 0xFF in _BUSY_CODES


def after_commit(session: AsyncSession, callback: Callable[[], object]) -> None:
    """
    Run ``callback`` once the request's transaction has committed, and never if
    it rolls back. Used for in-memory state that must not get ahead of the
    database, such as ending every vault session after a master password
    change.
    """
    session.info.setdefault(_AFTER_COMMIT, []).append(callback)


def after_rollback(session: AsyncSession, callback: Callable[[], object]) -> None:
    """Run ``callback`` if the request's transaction rolls back instead."""
    session.info.setdefault(_AFTER_ROLLBACK, []).append(callback)


def _run(session: AsyncSession, hooks: str) -> None:
    callbacks = session.info.pop(hooks, [])
    session.info.pop(_AFTER_COMMIT, None)
    session.info.pop(_AFTER_ROLLBACK, None)
    for callback in callbacks:
        callback()


class Database:
    """
    The SQLite vault of one app instance. The engine is created on first use,
    so building an app opens no file.

    Read transactions are deferred and see one consistent WAL snapshot next to
    a running writer. A connection that raised a database error is discarded
    instead of returned to the pool: Python's sqlite3 module leaves a statement
    that failed while fetching (a value it cannot decode, for example) un-
    reset, and that statement would keep its old snapshot open, so every later
    write on the connection would fail as busy. Write transactions start with
    BEGIN IMMEDIATE, which takes SQLite's single write lock before their first
    read, so every write request checks its session key, reads and writes as
    one serialized unit, and a master password change can never interleave with
    another write.
    """

    def __init__(
        self, data_dir: Path | None = None, *, engine: AsyncEngine | None = None
    ) -> None:
        self._data_dir = data_dir
        self._engine = engine
        self._sessions: dict[bool, async_sessionmaker[AsyncSession]] = {}

    @property
    def data_dir(self) -> Path:
        return self._data_dir or get_storage_settings().data_dir

    @property
    def path(self) -> Path:
        return vault_file(self.data_dir)

    @property
    def engine(self) -> AsyncEngine:
        if self._engine is None:
            self._engine = create_engine(self.path)
        return self._engine

    def writer(self) -> AsyncEngine:
        return self.engine.execution_options(**{_BEGIN: "IMMEDIATE"})

    def sessions(self, *, write: bool = True) -> async_sessionmaker[AsyncSession]:
        if write not in self._sessions:
            self._sessions[write] = async_sessionmaker(
                self.writer() if write else self.engine,
                expire_on_commit=False,
                class_=AsyncSession,
            )
        return self._sessions[write]

    @asynccontextmanager
    async def transaction(self, *, write: bool = True) -> AsyncIterator[AsyncSession]:
        async with self.sessions(write=write)() as session:
            try:
                yield session
                await session.commit()
            except BaseException as error:
                try:
                    if isinstance(error, DBAPIError):
                        await session.invalidate()
                    else:
                        await session.rollback()
                finally:
                    _run(session, _AFTER_ROLLBACK)
                if (
                    isinstance(error, OperationalError) and is_busy(error)
                ) or isinstance(error, PoolTimeout):
                    raise VaultBusy(_BUSY_DETAIL) from error
                raise
            _run(session, _AFTER_COMMIT)

    async def prepare(self) -> None:
        """Create or open the vault file: folder and file modes, a read-only
        identity and integrity check of an existing file, then the schema."""
        await asyncio.to_thread(prepare_data_dir, self.data_dir)
        try:
            async with self.writer().begin() as connection:
                await connection.run_sync(ensure_schema)
        except DatabaseError as error:
            raise StorageError(
                f"SQLite cannot open the vault file {self.path}: {error.orig}. "
                "Restore a snapshot (docs/UPDATING.md)."
            ) from error

    async def dispose(self) -> None:
        if self._engine is not None:
            await self._engine.dispose()
