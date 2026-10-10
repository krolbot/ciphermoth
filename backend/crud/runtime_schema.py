from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

_KEY_CHECK_EXISTS = text(
    "SELECT 1 FROM information_schema.columns "
    "WHERE table_schema = current_schema() "
    "AND table_name = 'master_password' AND column_name = 'key_check'"
)
_ADD_KEY_CHECK = text(
    "ALTER TABLE master_password ADD COLUMN IF NOT EXISTS key_check BYTEA"
)


async def ensure_runtime_schema(engine: AsyncEngine) -> None:
    """
    Add the nullable ``master_password.key_check`` column outside Alembic.

    Up to v1.4.5 the container runs ``alembic upgrade head`` on start and refuses
    to boot when the database carries a revision it does not know, and the
    one-click updater rolls back by restarting the previous image. A new Alembic
    revision would therefore leave a rolled-back vault unable to start. An
    additive nullable column keeps the revision unchanged, and older releases
    simply ignore it.
    """
    async with engine.begin() as conn:
        if await conn.scalar(_KEY_CHECK_EXISTS) is None:
            await conn.execute(_ADD_KEY_CHECK)
