from __future__ import annotations
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.utils.string_tools import build_database_url


def build_engine() -> AsyncEngine:
    """根据当前配置构建异步数据库引擎。"""

    database_url = build_database_url(
        db_engine=settings.db_engine,
        db_driver=settings.db_driver,
        db_host=settings.db_host,
        db_port=settings.db_port,
        db_name=settings.db_name,
        db_user=settings.db_user,
        db_password=settings.db_password,
        db_sqlite_path=settings.db_sqlite_path,
    )

    # ✅ 关键修复：SQLite 必须使用 async driver
    if database_url.startswith("sqlite"):
        # 如果已经是 sqlite+aiosqlite 就不重复改
        if "+aiosqlite" not in database_url:
            if "///" in database_url:
                database_url = database_url.replace("sqlite:///", "sqlite+aiosqlite:///")
            else:
                database_url = database_url.replace("sqlite://", "sqlite+aiosqlite://")

        connect_args = {"check_same_thread": False}
    else:
        connect_args = {}

    return create_async_engine(
        database_url,
        echo=False,
        connect_args=connect_args,
    )


engine = build_engine()

async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def create_db_and_tables() -> None:
    """创建所有表"""
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


async def drop_db_and_tables() -> None:
    """删除所有表"""
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI session dependency"""
    async with async_session_maker() as session:
        yield session