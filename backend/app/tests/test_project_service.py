from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core import config as config_module
from app.core import database as database_module
from app.models.project import Project, ProjectMember, ProjectMemberRole
from app.models.user import User
from app.schemas.project import ProjectCreate, ProjectUpdate
from app.services import project as project_service_module
from app.tests.base import EnvTestBase
from app.utils.string_tools import hash_password
from app.utils.time_tools import utc_now


class TestProjectService(EnvTestBase):
    """项目服务层测试。"""

    async def _create_user(
        self,
        session,
        username: str,
        is_superuser: bool = False,
        disabled: bool = False,
    ) -> User:
        """创建测试用户。"""
        now = utc_now()
        user = User(
            username=username,
            nickname=username,
            email=f"{username}@example.com",
            password_hash=hash_password("password123"),
            is_superuser=is_superuser,
            disabled_at=now if disabled else None,
            created_at=now,
            updated_at=now,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user

    async def _create_project(self, session, name: str, owner_public_id: str) -> Project:
        """创建测试项目。"""
        return await project_service_module.create_project(
            session,
            owner_public_id,
            ProjectCreate(name=name),
        )

    @pytest.mark.anyio
    async def test_create_project_creates_owner_member(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        """验证创建项目时自动添加 owner 成员。"""
        self.set_env(
            monkeypatch,
            {
                "DB_ENGINE": "sqlite",
                "DB_DRIVER": "aiosqlite",
                "DB_SQLITE_PATH": str(tmp_path / "create.db"),
            },
        )

        _, database, project_service = self.reload_modules(
            config_module,
            database_module,
            project_service_module,
        )

        await database.create_db_and_tables()
        try:
            async with database.async_session_maker() as session:
                user = await self._create_user(session, "owner1")

            async with database.async_session_maker() as session:
                project = await project_service.create_project(
                    session,
                    user.public_id,
                    ProjectCreate(name="新项目"),
                )

                assert project.id is not None
                assert project.name == "新项目"
                assert project.owner_id == user.public_id
                assert project.is_active is True

                member = await project_service.get_project_member(
                    session,
                    project.id,
                    user.public_id,
                    user.public_id,
                )
                assert member is not None
                assert member.role == ProjectMemberRole.OWNER
        finally:
            await database.drop_db_and_tables()
            await database.engine.dispose()

    @pytest.mark.anyio
    async def test_get_project_by_public_id_as_owner(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        """验证项目所有者可获取项目详情。"""
        self.set_env(
            monkeypatch,
            {
                "DB_ENGINE": "sqlite",
                "DB_DRIVER": "aiosqlite",
                "DB_SQLITE_PATH": str(tmp_path / "get.db"),
            },
        )

        _, database, project_service = self.reload_modules(
            config_module,
            database_module,
            project_service_module,
        )

        await database.create_db_and_tables()
        try:
            async with database.async_session_maker() as session:
                user = await self._create_user(session, "owner1")
                project = await self._create_project(session, "测试项目", user.public_id)

            async with database.async_session_maker() as session:
                fetched = await project_service.get_project_by_public_id(
                    session,
                    project.public_id,
                    user.public_id,
                )
                assert fetched is not None
                assert fetched.name == "测试项目"
        finally:
            await database.drop_db_and_tables()
            await database.engine.dispose()

    @pytest.mark.anyio
    async def test_get_project_or_raise_not_found(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        """验证获取不存在的项目抛出异常。"""
        self.set_env(
            monkeypatch,
            {
                "DB_ENGINE": "sqlite",
                "DB_DRIVER": "aiosqlite",
                "DB_SQLITE_PATH": str(tmp_path / "notfound.db"),
            },
        )

        _, database, project_service = self.reload_modules(
            config_module,
            database_module,
            project_service_module,
        )

        await database.create_db_and_tables()
        try:
            async with database.async_session_maker() as session:
                user = await self._create_user(session, "owner1")

            async with database.async_session_maker() as session:
                with pytest.raises(project_service.ProjectNotFoundError):
                    await project_service.get_project_or_raise(
                        session,
                        "nonexistent-id",
                        user.public_id,
                    )
        finally:
            await database.drop_db_and_tables()
            await database.engine.dispose()

    @pytest.mark.anyio
    async def test_non_member_cannot_access_project(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        """验证非项目成员无法访问项目。"""
        self.set_env(
            monkeypatch,
            {
                "DB_ENGINE": "sqlite",
                "DB_DRIVER": "aiosqlite",
                "DB_SQLITE_PATH": str(tmp_path / "access.db"),
            },
        )

        _, database, project_service = self.reload_modules(
            config_module,
            database_module,
            project_service_module,
        )

        await database.create_db_and_tables()
        try:
            async with database.async_session_maker() as session:
                owner = await self._create_user(session, "owner1")
                other = await self._create_user(session, "other")

            async with database.async_session_maker() as session:
                project = await self._create_project(session, "私有项目", owner.public_id)

            async with database.async_session_maker() as session:
                with pytest.raises(project_service.ProjectAccessDeniedError):
                    await project_service.get_project_by_public_id(
                        session,
                        project.public_id,
                        other.public_id,
                    )
        finally:
            await database.drop_db_and_tables()
            await database.engine.dispose()

    @pytest.mark.anyio
    async def test_superuser_can_access_any_project(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        """验证超级管理员可访问任意项目。"""
        self.set_env(
            monkeypatch,
            {
                "DB_ENGINE": "sqlite",
                "DB_DRIVER": "aiosqlite",
                "DB_SQLITE_PATH": str(tmp_path / "admin_access.db"),
            },
        )

        _, database, project_service = self.reload_modules(
            config_module,
            database_module,
            project_service_module,
        )

        await database.create_db_and_tables()
        try:
            async with database.async_session_maker() as session:
                owner = await self._create_user(session, "owner1")
                admin = await self._create_user(session, "admin", is_superuser=True)

            async with database.async_session_maker() as session:
                project = await self._create_project(session, "任意项目", owner.public_id)
                fetched = await project_service.get_project_by_public_id(
                    session,
                    project.public_id,
                    admin.public_id,
                )
                assert fetched is not None
        finally:
            await database.drop_db_and_tables()
            await database.engine.dispose()

    @pytest.mark.anyio
    async def test_list_own_projects(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        """验证用户只能列出自己有权限的项目。"""
        self.set_env(
            monkeypatch,
            {
                "DB_ENGINE": "sqlite",
                "DB_DRIVER": "aiosqlite",
                "DB_SQLITE_PATH": str(tmp_path / "list.db"),
            },
        )

        _, database, project_service = self.reload_modules(
            config_module,
            database_module,
            project_service_module,
        )

        await database.create_db_and_tables()
        try:
            async with database.async_session_maker() as session:
                user_a = await self._create_user(session, "user_a")
                user_b = await self._create_user(session, "user_b")

            async with database.async_session_maker() as session:
                await self._create_project(session, "A的项目", user_a.public_id)
                await self._create_project(session, "B的项目", user_b.public_id)

            async with database.async_session_maker() as session:
                projects = await project_service.list_projects(session, user_a.public_id)
                assert len(projects) == 1
                assert projects[0].name == "A的项目"
        finally:
            await database.drop_db_and_tables()
            await database.engine.dispose()

    @pytest.mark.anyio
    async def test_superuser_lists_all_projects(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        """验证超级管理员可列出全部项目。"""
        self.set_env(
            monkeypatch,
            {
                "DB_ENGINE": "sqlite",
                "DB_DRIVER": "aiosqlite",
                "DB_SQLITE_PATH": str(tmp_path / "admin_list.db"),
            },
        )

        _, database, project_service = self.reload_modules(
            config_module,
            database_module,
            project_service_module,
        )

        await database.create_db_and_tables()
        try:
            async with database.async_session_maker() as session:
                user_a = await self._create_user(session, "user_a")
                user_b = await self._create_user(session, "user_b")
                admin = await self._create_user(session, "admin", is_superuser=True)

            async with database.async_session_maker() as session:
                await self._create_project(session, "A的项目", user_a.public_id)
                await self._create_project(session, "B的项目", user_b.public_id)

            async with database.async_session_maker() as session:
                projects = await project_service.list_projects(session, admin.public_id)
                assert len(projects) == 2
        finally:
            await database.drop_db_and_tables()
            await database.engine.dispose()

    @pytest.mark.anyio
    async def test_search_projects_by_name(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        """验证按项目名搜索。"""
        self.set_env(
            monkeypatch,
            {
                "DB_ENGINE": "sqlite",
                "DB_DRIVER": "aiosqlite",
                "DB_SQLITE_PATH": str(tmp_path / "search_name.db"),
            },
        )

        _, database, project_service = self.reload_modules(
            config_module,
            database_module,
            project_service_module,
        )

        await database.create_db_and_tables()
        try:
            async with database.async_session_maker() as session:
                user = await self._create_user(session, "owner1")

            async with database.async_session_maker() as session:
                await self._create_project(session, "武侠小说转视频", user.public_id)
                await self._create_project(session, "科幻电影", user.public_id)

            async with database.async_session_maker() as session:
                results = await project_service.search_projects_by_name(
                    session,
                    user.public_id,
                    "武侠",
                )
                assert len(results) == 1
                assert results[0].name == "武侠小说转视频"

                results = await project_service.search_projects_by_name(
                    session,
                    user.public_id,
                    "影",
                )
                assert len(results) == 1
                assert results[0].name == "科幻电影"
        finally:
            await database.drop_db_and_tables()
            await database.engine.dispose()

    @pytest.mark.anyio
    async def test_update_project(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        """验证更新项目基础信息。"""
        self.set_env(
            monkeypatch,
            {
                "DB_ENGINE": "sqlite",
                "DB_DRIVER": "aiosqlite",
                "DB_SQLITE_PATH": str(tmp_path / "update.db"),
            },
        )

        _, database, project_service = self.reload_modules(
            config_module,
            database_module,
            project_service_module,
        )

        await database.create_db_and_tables()
        try:
            async with database.async_session_maker() as session:
                user = await self._create_user(session, "owner1")

            async with database.async_session_maker() as session:
                project = await self._create_project(session, "原始名称", user.public_id)

            async with database.async_session_maker() as session:
                updated = await project_service.update_project(
                    session,
                    project.public_id,
                    ProjectUpdate(name="新名称", intro="更新后的简介"),
                    user.public_id,
                )
                assert updated.name == "新名称"
                assert updated.intro == "更新后的简介"
        finally:
            await database.drop_db_and_tables()
            await database.engine.dispose()

    @pytest.mark.anyio
    async def test_disable_and_enable_project(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        """验证禁用和启用项目流程。"""
        self.set_env(
            monkeypatch,
            {
                "DB_ENGINE": "sqlite",
                "DB_DRIVER": "aiosqlite",
                "DB_SQLITE_PATH": str(tmp_path / "toggle.db"),
            },
        )

        _, database, project_service = self.reload_modules(
            config_module,
            database_module,
            project_service_module,
        )

        await database.create_db_and_tables()
        try:
            async with database.async_session_maker() as session:
                user = await self._create_user(session, "owner1")

            async with database.async_session_maker() as session:
                project = await self._create_project(session, "待禁用项目", user.public_id)

            async with database.async_session_maker() as session:
                disabled = await project_service.disable_project(
                    session,
                    project.public_id,
                    user.public_id,
                )
                assert disabled.is_disabled is True

            async with database.async_session_maker() as session:
                enabled = await project_service.enable_project(
                    session,
                    project.public_id,
                    user.public_id,
                )
                assert enabled.is_active is True
        finally:
            await database.drop_db_and_tables()
            await database.engine.dispose()

    @pytest.mark.anyio
    async def test_delete_project_also_removes_members(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        """验证删除项目同时移除成员关系。"""
        self.set_env(
            monkeypatch,
            {
                "DB_ENGINE": "sqlite",
                "DB_DRIVER": "aiosqlite",
                "DB_SQLITE_PATH": str(tmp_path / "delete.db"),
            },
        )

        _, database, project_service = self.reload_modules(
            config_module,
            database_module,
            project_service_module,
        )

        await database.create_db_and_tables()
        try:
            async with database.async_session_maker() as session:
                user = await self._create_user(session, "owner1")

            async with database.async_session_maker() as session:
                project = await self._create_project(session, "待删除项目", user.public_id)

            async with database.async_session_maker() as session:
                await project_service.delete_project(session, project.public_id, user.public_id)

            async with database.async_session_maker() as session:
                with pytest.raises(project_service.ProjectNotFoundError):
                    await project_service.get_project_or_raise(
                        session,
                        project.public_id,
                        user.public_id,
                    )
        finally:
            await database.drop_db_and_tables()
            await database.engine.dispose()

    @pytest.mark.anyio
    async def test_add_project_member(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        """验证新增项目成员。"""
        self.set_env(
            monkeypatch,
            {
                "DB_ENGINE": "sqlite",
                "DB_DRIVER": "aiosqlite",
                "DB_SQLITE_PATH": str(tmp_path / "add_member.db"),
            },
        )

        _, database, project_service = self.reload_modules(
            config_module,
            database_module,
            project_service_module,
        )

        await database.create_db_and_tables()
        try:
            async with database.async_session_maker() as session:
                owner = await self._create_user(session, "owner1")
                member_user = await self._create_user(session, "member1")

            async with database.async_session_maker() as session:
                project = await self._create_project(session, "成员测试项目", owner.public_id)

            async with database.async_session_maker() as session:
                member = await project_service.add_project_member(
                    session,
                    project.public_id,
                    member_user.public_id,
                    ProjectMemberRole.EDITOR,
                    owner.public_id,
                )
                assert member.role == ProjectMemberRole.EDITOR
                assert member.user_public_id == member_user.public_id

                members = await project_service.list_project_members(
                    session,
                    project.public_id,
                    owner.public_id,
                )
                assert len(members) == 2  # owner + editor
        finally:
            await database.drop_db_and_tables()
            await database.engine.dispose()

    @pytest.mark.anyio
    async def test_add_project_member_duplicate_raises_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        """验证重复添加项目成员抛出冲突异常。"""
        self.set_env(
            monkeypatch,
            {
                "DB_ENGINE": "sqlite",
                "DB_DRIVER": "aiosqlite",
                "DB_SQLITE_PATH": str(tmp_path / "dup_member.db"),
            },
        )

        _, database, project_service = self.reload_modules(
            config_module,
            database_module,
            project_service_module,
        )

        await database.create_db_and_tables()
        try:
            async with database.async_session_maker() as session:
                owner = await self._create_user(session, "owner1")
                member_user = await self._create_user(session, "member1")

            async with database.async_session_maker() as session:
                project = await self._create_project(session, "项目", owner.public_id)

            async with database.async_session_maker() as session:
                await project_service.add_project_member(
                    session,
                    project.public_id,
                    member_user.public_id,
                    ProjectMemberRole.EDITOR,
                    owner.public_id,
                )

                with pytest.raises(project_service.ProjectMemberConflictError):
                    await project_service.add_project_member(
                        session,
                        project.public_id,
                        member_user.public_id,
                        ProjectMemberRole.VIEWER,
                        owner.public_id,
                    )
        finally:
            await database.drop_db_and_tables()
            await database.engine.dispose()

    @pytest.mark.anyio
    async def test_update_project_member_role(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        """验证更新项目成员角色。"""
        self.set_env(
            monkeypatch,
            {
                "DB_ENGINE": "sqlite",
                "DB_DRIVER": "aiosqlite",
                "DB_SQLITE_PATH": str(tmp_path / "update_role.db"),
            },
        )

        _, database, project_service = self.reload_modules(
            config_module,
            database_module,
            project_service_module,
        )

        await database.create_db_and_tables()
        try:
            async with database.async_session_maker() as session:
                owner = await self._create_user(session, "owner1")
                member_user = await self._create_user(session, "member1")

            async with database.async_session_maker() as session:
                project = await self._create_project(session, "项目", owner.public_id)
                await project_service.add_project_member(
                    session,
                    project.public_id,
                    member_user.public_id,
                    ProjectMemberRole.VIEWER,
                    owner.public_id,
                )

            async with database.async_session_maker() as session:
                updated = await project_service.update_project_member_role(
                    session,
                    project.public_id,
                    member_user.public_id,
                    ProjectMemberRole.ADMIN,
                    owner.public_id,
                )
                assert updated.role == ProjectMemberRole.ADMIN
        finally:
            await database.drop_db_and_tables()
            await database.engine.dispose()

    @pytest.mark.anyio
    async def test_remove_project_member(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        """验证移除项目成员。"""
        self.set_env(
            monkeypatch,
            {
                "DB_ENGINE": "sqlite",
                "DB_DRIVER": "aiosqlite",
                "DB_SQLITE_PATH": str(tmp_path / "remove_member.db"),
            },
        )

        _, database, project_service = self.reload_modules(
            config_module,
            database_module,
            project_service_module,
        )

        await database.create_db_and_tables()
        try:
            async with database.async_session_maker() as session:
                owner = await self._create_user(session, "owner1")
                member_user = await self._create_user(session, "member1")

            async with database.async_session_maker() as session:
                project = await self._create_project(session, "项目", owner.public_id)
                await project_service.add_project_member(
                    session,
                    project.public_id,
                    member_user.public_id,
                    ProjectMemberRole.VIEWER,
                    owner.public_id,
                )

            async with database.async_session_maker() as session:
                members_before = await project_service.list_project_members(
                    session,
                    project.public_id,
                    owner.public_id,
                )
                assert len(members_before) == 2

            async with database.async_session_maker() as session:
                await project_service.remove_project_member(
                    session,
                    project.public_id,
                    member_user.public_id,
                    owner.public_id,
                )

                members_after = await project_service.list_project_members(
                    session,
                    project.public_id,
                    owner.public_id,
                )
                assert len(members_after) == 1
                assert members_after[0].role == ProjectMemberRole.OWNER
        finally:
            await database.drop_db_and_tables()
            await database.engine.dispose()

    @pytest.mark.anyio
    async def test_invite_project_member(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        """验证邀请项目成员。"""
        self.set_env(
            monkeypatch,
            {
                "DB_ENGINE": "sqlite",
                "DB_DRIVER": "aiosqlite",
                "DB_SQLITE_PATH": str(tmp_path / "invite.db"),
            },
        )

        _, database, project_service = self.reload_modules(
            config_module,
            database_module,
            project_service_module,
        )

        await database.create_db_and_tables()
        try:
            async with database.async_session_maker() as session:
                owner = await self._create_user(session, "owner1")
                invitee = await self._create_user(session, "invitee")

            async with database.async_session_maker() as session:
                project = await self._create_project(session, "项目", owner.public_id)

            async with database.async_session_maker() as session:
                member = await project_service.invite_project_member(
                    session,
                    project.public_id,
                    invitee.public_id,
                    ProjectMemberRole.MANAGER,
                    owner.public_id,
                )
                assert member.role == ProjectMemberRole.MANAGER
                assert member.user_public_id == invitee.public_id
        finally:
            await database.drop_db_and_tables()
            await database.engine.dispose()

    @pytest.mark.anyio
    async def test_invite_nonexistent_user_raises_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        """验证邀请不存在的用户抛出异常。"""
        self.set_env(
            monkeypatch,
            {
                "DB_ENGINE": "sqlite",
                "DB_DRIVER": "aiosqlite",
                "DB_SQLITE_PATH": str(tmp_path / "invite_404.db"),
            },
        )

        _, database, project_service = self.reload_modules(
            config_module,
            database_module,
            project_service_module,
        )

        await database.create_db_and_tables()
        try:
            async with database.async_session_maker() as session:
                owner = await self._create_user(session, "owner1")

            async with database.async_session_maker() as session:
                project = await self._create_project(session, "项目", owner.public_id)

            async with database.async_session_maker() as session:
                with pytest.raises(project_service.ProjectMemberNotFoundError):
                    await project_service.invite_project_member(
                        session,
                        project.public_id,
                        "nonexistent-user-id",
                        ProjectMemberRole.VIEWER,
                        owner.public_id,
                    )
        finally:
            await database.drop_db_and_tables()
            await database.engine.dispose()

    @pytest.mark.anyio
    async def test_search_project_member_candidates(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        """验证搜索可邀请项目成员。"""
        self.set_env(
            monkeypatch,
            {
                "DB_ENGINE": "sqlite",
                "DB_DRIVER": "aiosqlite",
                "DB_SQLITE_PATH": str(tmp_path / "candidates.db"),
            },
        )

        _, database, project_service = self.reload_modules(
            config_module,
            database_module,
            project_service_module,
        )

        await database.create_db_and_tables()
        try:
            async with database.async_session_maker() as session:
                owner = await self._create_user(session, "owner1")
                user_a = await self._create_user(session, "alice")
                user_b = await self._create_user(session, "bob")

            async with database.async_session_maker() as session:
                project = await self._create_project(session, "项目", owner.public_id)
                await project_service.add_project_member(
                    session,
                    project.public_id,
                    user_a.public_id,
                    ProjectMemberRole.EDITOR,
                    owner.public_id,
                )

            async with database.async_session_maker() as session:
                candidates = await project_service.search_project_member_candidates(
                    session,
                    project.public_id,
                    "bob",
                    owner.public_id,
                )
                assert len(candidates) == 1
                assert candidates[0].username == "bob"

                candidates = await project_service.search_project_member_candidates(
                    session,
                    project.public_id,
                    "alice",
                    owner.public_id,
                )
                # alice 已在项目中，不应出现在候选列表
                assert len(candidates) == 0
        finally:
            await database.drop_db_and_tables()
            await database.engine.dispose()

    @pytest.mark.anyio
    async def test_member_can_access_project(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        """验证项目成员可访问项目。"""
        self.set_env(
            monkeypatch,
            {
                "DB_ENGINE": "sqlite",
                "DB_DRIVER": "aiosqlite",
                "DB_SQLITE_PATH": str(tmp_path / "member_access.db"),
            },
        )

        _, database, project_service = self.reload_modules(
            config_module,
            database_module,
            project_service_module,
        )

        await database.create_db_and_tables()
        try:
            async with database.async_session_maker() as session:
                owner = await self._create_user(session, "owner1")
                member_user = await self._create_user(session, "member1")

            async with database.async_session_maker() as session:
                project = await self._create_project(session, "共享项目", owner.public_id)
                await project_service.add_project_member(
                    session,
                    project.public_id,
                    member_user.public_id,
                    ProjectMemberRole.EDITOR,
                    owner.public_id,
                )

            async with database.async_session_maker() as session:
                fetched = await project_service.get_project_by_public_id(
                    session,
                    project.public_id,
                    member_user.public_id,
                )
                assert fetched is not None
                assert fetched.name == "共享项目"
        finally:
            await database.drop_db_and_tables()
            await database.engine.dispose()

    @pytest.mark.anyio
    async def test_search_projects_by_member(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        """验证按项目成员搜索项目。"""
        self.set_env(
            monkeypatch,
            {
                "DB_ENGINE": "sqlite",
                "DB_DRIVER": "aiosqlite",
                "DB_SQLITE_PATH": str(tmp_path / "search_member.db"),
            },
        )

        _, database, project_service = self.reload_modules(
            config_module,
            database_module,
            project_service_module,
        )

        await database.create_db_and_tables()
        try:
            async with database.async_session_maker() as session:
                owner = await self._create_user(session, "owner1")
                member = await self._create_user(session, "member1")
                other = await self._create_user(session, "other")

            async with database.async_session_maker() as session:
                p1 = await self._create_project(session, "项目一", owner.public_id)
                p2 = await self._create_project(session, "项目二", member.public_id)
                await project_service.add_project_member(
                    session,
                    p1.public_id,
                    member.public_id,
                    ProjectMemberRole.EDITOR,
                    owner.public_id,
                )
                # 将 owner 加入 p2，使其有权限查看 p2
                await project_service.add_project_member(
                    session,
                    p2.public_id,
                    owner.public_id,
                    ProjectMemberRole.EDITOR,
                    member.public_id,
                )

            async with database.async_session_maker() as session:
                results = await project_service.search_projects_by_member(
                    session,
                    owner.public_id,
                    member.public_id,
                )
                # owner 可访问 2 个项目：p1（owner_id=owner）和 p2（owner 是其成员）
                # member 是 p1 的成员且是 p2 的 owner，因此都匹配
                assert len(results) == 2
        finally:
            await database.drop_db_and_tables()
            await database.engine.dispose()
