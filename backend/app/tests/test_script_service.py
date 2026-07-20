from __future__ import annotations

import pytest
from sqlmodel import select

from app.core import config as config_module
from app.core import database as database_module
from app.models.screenwriting import ScreenwritingSession
from app.models.user import User
from app.schemas.project import ProjectCreate
from app.services import project as project_service
from app.services import script as script_service
from app.tests.base import EnvTestBase
from app.utils.string_tools import hash_password


VISIBLE_SCRIPT = """# 测试项目 EP01：第一次同步

## 剧情梗概
主角发现关键线索并决定立刻展开调查。

1-1 仓库 夜 内
人物：主角
△ 主角推开仓库大门。
主角：这里一定藏着答案。
"""


class TestScriptService(EnvTestBase):
    @pytest.mark.anyio
    async def test_sync_current_workspace_uses_visible_script_from_request(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        """页面文本比持久化会话新时，同步应以用户当前看到的文本为准。"""
        self.set_env(
            monkeypatch,
            {
                "DB_ENGINE": "sqlite",
                "DB_DRIVER": "aiosqlite",
                "DB_SQLITE_PATH": str(tmp_path / "script_sync.db"),
            },
        )
        _, database = self.reload_modules(config_module, database_module)

        await database.create_db_and_tables()
        try:
            async with database.async_session_maker() as session:
                user = User(
                    username="script_owner",
                    nickname="script_owner",
                    email="script_owner@example.com",
                    password_hash=hash_password("password123"),
                )
                session.add(user)
                await session.commit()
                await session.refresh(user)
                project = await project_service.create_project(
                    session,
                    user.public_id,
                    ProjectCreate(name="测试项目"),
                )

            async with database.async_session_maker() as session:
                plan = await script_service.sync_current_workspace(
                    session,
                    project.public_id,
                    user.public_id,
                    script_content=VISIBLE_SCRIPT,
                )
                await session.commit()
                _, episodes = await script_service.get_plan_detail(
                    session,
                    project.public_id,
                    user.public_id,
                    plan.public_id,
                )

            assert len(episodes) == 1
            assert episodes[0].episode_index == 1
            assert episodes[0].title == "第一次同步"
            assert episodes[0].body == VISIBLE_SCRIPT.strip()
        finally:
            await database.drop_db_and_tables()
            await database.engine.dispose()

    @pytest.mark.anyio
    async def test_sync_failure_preserves_visible_script_in_workspace(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        """同步解析失败时，页面正文也必须先持久化，避免返回页面后丢失。"""
        self.set_env(
            monkeypatch,
            {
                "DB_ENGINE": "sqlite",
                "DB_DRIVER": "aiosqlite",
                "DB_SQLITE_PATH": str(tmp_path / "script_sync_failure.db"),
            },
        )
        _, database = self.reload_modules(config_module, database_module)

        await database.create_db_and_tables()
        try:
            async with database.async_session_maker() as session:
                user = User(
                    username="failed_sync_owner",
                    nickname="failed_sync_owner",
                    email="failed_sync_owner@example.com",
                    password_hash=hash_password("password123"),
                )
                session.add(user)
                await session.commit()
                await session.refresh(user)
                project = await project_service.create_project(
                    session,
                    user.public_id,
                    ProjectCreate(name="同步失败项目"),
                )

            visible_script = "这是页面已经展示、但暂时无法解析为分集的剧本正文。"
            async with database.async_session_maker() as session:
                with pytest.raises(script_service.ScriptServiceError):
                    await script_service.sync_current_workspace(
                        session,
                        project.public_id,
                        user.public_id,
                        script_content=visible_script,
                    )

            async with database.async_session_maker() as session:
                persisted = (
                    await session.exec(
                        select(ScreenwritingSession).where(
                            ScreenwritingSession.project_id == project.id,
                            ScreenwritingSession.user_public_id == user.public_id,
                        )
                    )
                ).first()

            assert persisted is not None
            assert persisted.script == visible_script
            assert persisted.active_tab == "script"
        finally:
            await database.drop_db_and_tables()
            await database.engine.dispose()
