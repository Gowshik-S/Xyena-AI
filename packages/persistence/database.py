from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from packages.config import get_settings


class Database:
    def __init__(self, url: str) -> None:
        self.engine: AsyncEngine = create_async_engine(
            url,
            pool_pre_ping=True,
            pool_recycle=1800,
            connect_args={"server_settings": {"application_name": "xyena-backend"}}
            if url.startswith("postgresql+asyncpg")
            else {},
        )
        self.session_factory = async_sessionmaker(
            bind=self.engine,
            expire_on_commit=False,
            autoflush=False,
        )

    @asynccontextmanager
    async def session(
        self,
        *,
        tenant_id: UUID | None = None,
        user_id: UUID | None = None,
        service_role: str | None = None,
    ) -> AsyncIterator[AsyncSession]:
        async with self.session_factory() as session:
            async with session.begin():
                if tenant_id is not None:
                    await session.execute(
                        text("SELECT set_config('app.tenant_id', :value, true)"),
                        {"value": str(tenant_id)},
                    )
                if user_id is not None:
                    await session.execute(
                        text("SELECT set_config('app.user_id', :value, true)"),
                        {"value": str(user_id)},
                    )
                if service_role is not None:
                    await session.execute(
                        text("SELECT set_config('app.service_role', :value, true)"),
                        {"value": service_role},
                    )
                yield session

    async def dispose(self) -> None:
        await self.engine.dispose()


@lru_cache(maxsize=1)
def get_database() -> Database:
    return Database(get_settings().database_url)

