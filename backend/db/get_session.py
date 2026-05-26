from collections.abc import AsyncIterator
from typing import cast

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    sessionmaker = cast(
        async_sessionmaker[AsyncSession],
        request.app.state.db_sessionmaker,
    )

    async with sessionmaker() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
