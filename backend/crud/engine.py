from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from urllib.parse import quote

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from settings import DBSettings, get_db_settings

_AFTER_COMMIT = "ciphermoth_after_commit"
_AFTER_ROLLBACK = "ciphermoth_after_rollback"


def database_url(settings: DBSettings | None = None) -> str:
    db = settings or get_db_settings()
    return (
        f"postgresql+asyncpg://{db.postgres_user}:{quote(db.postgres_password)}"
        f"@{db.postgres_host}:{db.postgres_port}/{db.postgres_db}"
    )


def create_engine(url: str | None = None) -> AsyncEngine:
    return create_async_engine(
        url or database_url(),
        pool_pre_ping=True,
        pool_size=5,
        pool_recycle=get_db_settings().pool_recycle,
    )


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
    The vault database of one app instance. The engine is created on first use,
    so building an app does not import a database driver or open a connection.
    """

    def __init__(
        self, url: str | None = None, *, engine: AsyncEngine | None = None
    ) -> None:
        self._url = url
        self._engine = engine
        self._sessions: async_sessionmaker[AsyncSession] | None = None

    @property
    def engine(self) -> AsyncEngine:
        if self._engine is None:
            self._engine = create_engine(self._url)
        return self._engine

    def sessions(self) -> async_sessionmaker[AsyncSession]:
        if self._sessions is None:
            self._sessions = async_sessionmaker(
                self.engine, expire_on_commit=False, class_=AsyncSession
            )
        return self._sessions

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[AsyncSession]:
        async with self.sessions()() as session:
            try:
                yield session
                await session.commit()
            except BaseException:
                try:
                    await session.rollback()
                finally:
                    _run(session, _AFTER_ROLLBACK)
                raise
            _run(session, _AFTER_COMMIT)

    async def dispose(self) -> None:
        if self._engine is not None:
            await self._engine.dispose()
