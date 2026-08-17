from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import MasterPasswordModel


async def fetch_master_password(
    session: AsyncSession,
) -> MasterPasswordModel | None:
    return await session.scalar(
        select(MasterPasswordModel)
        .where(MasterPasswordModel.deleted.is_(None))
        .order_by(MasterPasswordModel.id)
        .limit(1)
    )
