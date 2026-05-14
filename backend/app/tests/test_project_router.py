from __future__ import annotations

import jwt
from httpx import ASGITransport, AsyncClient
import pytest

from app import main as main_module
from app.core import config as config_module
from app.core import database as database_module
from app.middlewares import common as common_middleware_module
from app.models.project import ProjectMemberRole
from app.models.user import User
from app.routers import api as api_module
from app.routers import project as project_router_module
from app.routers import user as user_router_module
from app.schemas.project import ProjectCreate
from app.services import project as project_service_module
from app.tests.base import EnvTestBase
from app.utils import jwt_tools as jwt_tools_module
from app.utils.string_tools import hash_password
from app.utils.time_tools import utc_now


class TestProjectRouter(EnvTestBase):
    """项目路由层测试。"""

    async def _setup_user(
        self,
        database,
        username: str,
        is_superuser: bool = False,
    ) -> User:
        """创建测试用户并返回数据库实体。"""
        now = utc_now()
        async with database.async_session_maker() as session:
            user = User(
                username=username,
                nickname=username,
                email=f"{username}@example.com",
                password_hash=hash_password("password123"),
                is_superuser=is_superuser,
                created_at=now,
                updated_at=now,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user

    def _make_token(self, public_id: str, username: str, secret_key: str, algorithm: str) -> str:
        """生成有效的 access token，绕过 Redis 依赖。"""
        now = utc_now()
        from datetime import timedelta

        expire = now + timedelta(hours=1)
        from uuid import uuid4

        payload = {
            "sub": public_id,
            "username": username,
            "type": "access",
            "jti": uuid4().hex,
            "iat": int(now.timestamp()),
            "exp": int(expire.timestamp()),
        }
        return jwt.encode(payload, secret_key, algorithm=algorithm)

    def _patch_jwt(self, monkeypatch: pytest.MonkeyPatch, secret_key: str, algorithm: str) -> None:
        """绕过 Redis 依赖：替换 cache_token 和 common 中间件中的 decode_token。"""
        monkeypatch.setattr(jwt_tools_module, "cache_token", _noop_cache_token)
        monkeypatch.setattr(
            common_middleware_module,
            "decode_token",
            _no_redis_decode_token(secret_key, algorithm),
        )

    @pytest.mark.anyio
    async def test_create_project_returns_201(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        """验证创建项目返回 201。"""
        self.set_env(
            monkeypatch,
            {
                "DB_ENGINE": "sqlite",
                "DB_DRIVER": "aiosqlite",
                "DB_SQLITE_PATH": str(tmp_path / "router_create.db"),
            },
        )

        config, database, _, _, _, _, main, _ = self.reload_modules(
            config_module,
            database_module,
            jwt_tools_module,
            project_router_module,
            user_router_module,
            api_module,
            main_module,
            common_middleware_module,
        )

        self._patch_jwt(monkeypatch, config.settings.secret_key, config.settings.algorithm)

        await database.create_db_and_tables()
        try:
            user = await self._setup_user(database, "owner1")
            token = self._make_token(
                user.public_id,
                user.username,
                config.settings.secret_key,
                config.settings.algorithm,
            )

            app = main.create_app()
            transport = ASGITransport(app=app)

            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                response = await client.post(
                    "/api/projects/",
                    json={"name": "新项目"},
                    headers={"Authorization": f"Bearer {token}"},
                )

            assert response.status_code == 201
            data = response.json()
            assert data["name"] == "新项目"
            assert data["public_id"] is not None
            assert data["owner_id"] == user.public_id
        finally:
            await database.drop_db_and_tables()
            await database.engine.dispose()

    @pytest.mark.anyio
    async def test_create_project_without_token_returns_401(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        """验证未携带 token 创建项目返回 401。"""
        self.set_env(
            monkeypatch,
            {
                "DB_ENGINE": "sqlite",
                "DB_DRIVER": "aiosqlite",
                "DB_SQLITE_PATH": str(tmp_path / "router_noauth.db"),
            },
        )

        _, database, _, _, _, main, _ = self.reload_modules(
            config_module,
            database_module,
            project_router_module,
            user_router_module,
            api_module,
            main_module,
            common_middleware_module,
        )

        await database.create_db_and_tables()
        try:
            app = main.create_app()
            transport = ASGITransport(app=app)

            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                response = await client.post(
                    "/api/projects/",
                    json={"name": "未授权项目"},
                )

            assert response.status_code == 401
        finally:
            await database.drop_db_and_tables()
            await database.engine.dispose()

    @pytest.mark.anyio
    async def test_list_projects_returns_own_projects(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        """验证获取项目列表只返回用户自己的项目。"""
        self.set_env(
            monkeypatch,
            {
                "DB_ENGINE": "sqlite",
                "DB_DRIVER": "aiosqlite",
                "DB_SQLITE_PATH": str(tmp_path / "router_list.db"),
            },
        )

        config, database, _, _, _, _, main, _ = self.reload_modules(
            config_module,
            database_module,
            jwt_tools_module,
            project_router_module,
            user_router_module,
            api_module,
            main_module,
            common_middleware_module,
        )

        self._patch_jwt(monkeypatch, config.settings.secret_key, config.settings.algorithm)

        await database.create_db_and_tables()
        try:
            user_a = await self._setup_user(database, "user_a")
            user_b = await self._setup_user(database, "user_b")

            async with database.async_session_maker() as session:
                await project_service_module.create_project(session, user_a.public_id, ProjectCreate(name="A的项目"))
                await project_service_module.create_project(session, user_b.public_id, ProjectCreate(name="B的项目"))

            token_a = self._make_token(
                user_a.public_id,
                user_a.username,
                config.settings.secret_key,
                config.settings.algorithm,
            )

            app = main.create_app()
            transport = ASGITransport(app=app)

            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                response = await client.get(
                    "/api/projects/",
                    headers={"Authorization": f"Bearer {token_a}"},
                )

            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]["name"] == "A的项目"
        finally:
            await database.drop_db_and_tables()
            await database.engine.dispose()

    @pytest.mark.anyio
    async def test_get_project_detail(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        """验证获取项目详情。"""
        self.set_env(
            monkeypatch,
            {
                "DB_ENGINE": "sqlite",
                "DB_DRIVER": "aiosqlite",
                "DB_SQLITE_PATH": str(tmp_path / "router_detail.db"),
            },
        )

        config, database, _, _, _, _, main, _ = self.reload_modules(
            config_module,
            database_module,
            jwt_tools_module,
            project_router_module,
            user_router_module,
            api_module,
            main_module,
            common_middleware_module,
        )

        self._patch_jwt(monkeypatch, config.settings.secret_key, config.settings.algorithm)

        await database.create_db_and_tables()
        try:
            user = await self._setup_user(database, "owner1")

            async with database.async_session_maker() as session:
                project = await project_service_module.create_project(session, user.public_id, ProjectCreate(name="详情项目"))

            token = self._make_token(user.public_id, user.username, config.settings.secret_key, config.settings.algorithm)

            app = main.create_app()
            transport = ASGITransport(app=app)

            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                response = await client.get(
                    f"/api/projects/{project.public_id}",
                    headers={"Authorization": f"Bearer {token}"},
                )

            assert response.status_code == 200
            data = response.json()
            assert data["name"] == "详情项目"
            assert data["owner_id"] == user.public_id
        finally:
            await database.drop_db_and_tables()
            await database.engine.dispose()

    @pytest.mark.anyio
    async def test_get_nonexistent_project_returns_404(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        """验证获取不存在的项目返回 404。"""
        self.set_env(
            monkeypatch,
            {
                "DB_ENGINE": "sqlite",
                "DB_DRIVER": "aiosqlite",
                "DB_SQLITE_PATH": str(tmp_path / "router_404.db"),
            },
        )

        config, database, _, _, _, _, main, _ = self.reload_modules(
            config_module,
            database_module,
            jwt_tools_module,
            project_router_module,
            user_router_module,
            api_module,
            main_module,
            common_middleware_module,
        )

        self._patch_jwt(monkeypatch, config.settings.secret_key, config.settings.algorithm)

        await database.create_db_and_tables()
        try:
            user = await self._setup_user(database, "owner1")
            token = self._make_token(user.public_id, user.username, config.settings.secret_key, config.settings.algorithm)

            app = main.create_app()
            transport = ASGITransport(app=app)

            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                response = await client.get(
                    "/api/projects/nonexistent-id",
                    headers={"Authorization": f"Bearer {token}"},
                )

            assert response.status_code == 404
        finally:
            await database.drop_db_and_tables()
            await database.engine.dispose()

    @pytest.mark.anyio
    async def test_update_project(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        """验证更新项目。"""
        self.set_env(
            monkeypatch,
            {
                "DB_ENGINE": "sqlite",
                "DB_DRIVER": "aiosqlite",
                "DB_SQLITE_PATH": str(tmp_path / "router_update.db"),
            },
        )

        config, database, _, _, _, _, main, _ = self.reload_modules(
            config_module,
            database_module,
            jwt_tools_module,
            project_router_module,
            user_router_module,
            api_module,
            main_module,
            common_middleware_module,
        )

        self._patch_jwt(monkeypatch, config.settings.secret_key, config.settings.algorithm)

        await database.create_db_and_tables()
        try:
            user = await self._setup_user(database, "owner1")

            async with database.async_session_maker() as session:
                project = await project_service_module.create_project(session, user.public_id, ProjectCreate(name="原始名"))

            token = self._make_token(user.public_id, user.username, config.settings.secret_key, config.settings.algorithm)

            app = main.create_app()
            transport = ASGITransport(app=app)

            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                response = await client.put(
                    f"/api/projects/{project.public_id}",
                    json={"name": "更新名", "intro": "新的简介"},
                    headers={"Authorization": f"Bearer {token}"},
                )

            assert response.status_code == 200
            data = response.json()
            assert data["name"] == "更新名"
            assert data["intro"] == "新的简介"
        finally:
            await database.drop_db_and_tables()
            await database.engine.dispose()

    @pytest.mark.anyio
    async def test_disable_and_enable_project(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        """验证禁用和启用项目 API。"""
        self.set_env(
            monkeypatch,
            {
                "DB_ENGINE": "sqlite",
                "DB_DRIVER": "aiosqlite",
                "DB_SQLITE_PATH": str(tmp_path / "router_toggle.db"),
            },
        )

        config, database, _, _, _, _, main, _ = self.reload_modules(
            config_module,
            database_module,
            jwt_tools_module,
            project_router_module,
            user_router_module,
            api_module,
            main_module,
            common_middleware_module,
        )

        self._patch_jwt(monkeypatch, config.settings.secret_key, config.settings.algorithm)

        await database.create_db_and_tables()
        try:
            user = await self._setup_user(database, "owner1")

            async with database.async_session_maker() as session:
                project = await project_service_module.create_project(session, user.public_id, ProjectCreate(name="状态切换"))

            token = self._make_token(user.public_id, user.username, config.settings.secret_key, config.settings.algorithm)

            app = main.create_app()
            transport = ASGITransport(app=app)

            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                disable_resp = await client.patch(
                    f"/api/projects/{project.public_id}/disable",
                    headers={"Authorization": f"Bearer {token}"},
                )
                assert disable_resp.status_code == 200
                assert disable_resp.json()["disabled_at"] is not None

                enable_resp = await client.patch(
                    f"/api/projects/{project.public_id}/enable",
                    headers={"Authorization": f"Bearer {token}"},
                )
                assert enable_resp.status_code == 200
                assert enable_resp.json()["disabled_at"] is None
        finally:
            await database.drop_db_and_tables()
            await database.engine.dispose()

    @pytest.mark.anyio
    async def test_delete_project_returns_204(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        """验证删除项目返回 204。"""
        self.set_env(
            monkeypatch,
            {
                "DB_ENGINE": "sqlite",
                "DB_DRIVER": "aiosqlite",
                "DB_SQLITE_PATH": str(tmp_path / "router_delete.db"),
            },
        )

        config, database, _, _, _, _, main, _ = self.reload_modules(
            config_module,
            database_module,
            jwt_tools_module,
            project_router_module,
            user_router_module,
            api_module,
            main_module,
            common_middleware_module,
        )

        self._patch_jwt(monkeypatch, config.settings.secret_key, config.settings.algorithm)

        await database.create_db_and_tables()
        try:
            user = await self._setup_user(database, "owner1")

            async with database.async_session_maker() as session:
                project = await project_service_module.create_project(session, user.public_id, ProjectCreate(name="待删除"))

            token = self._make_token(user.public_id, user.username, config.settings.secret_key, config.settings.algorithm)

            app = main.create_app()
            transport = ASGITransport(app=app)

            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                response = await client.delete(
                    f"/api/projects/{project.public_id}",
                    headers={"Authorization": f"Bearer {token}"},
                )

            assert response.status_code == 204

            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                response = await client.get(
                    f"/api/projects/{project.public_id}",
                    headers={"Authorization": f"Bearer {token}"},
                )
            assert response.status_code == 404
        finally:
            await database.drop_db_and_tables()
            await database.engine.dispose()

    @pytest.mark.anyio
    async def test_search_projects_by_name(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        """验证按名称搜索项目 API。"""
        self.set_env(
            monkeypatch,
            {
                "DB_ENGINE": "sqlite",
                "DB_DRIVER": "aiosqlite",
                "DB_SQLITE_PATH": str(tmp_path / "router_search_name.db"),
            },
        )

        config, database, _, _, _, _, main, _ = self.reload_modules(
            config_module,
            database_module,
            jwt_tools_module,
            project_router_module,
            user_router_module,
            api_module,
            main_module,
            common_middleware_module,
        )

        self._patch_jwt(monkeypatch, config.settings.secret_key, config.settings.algorithm)

        await database.create_db_and_tables()
        try:
            user = await self._setup_user(database, "owner1")

            async with database.async_session_maker() as session:
                await project_service_module.create_project(session, user.public_id, ProjectCreate(name="武侠小说"))
                await project_service_module.create_project(session, user.public_id, ProjectCreate(name="科幻电影"))

            token = self._make_token(user.public_id, user.username, config.settings.secret_key, config.settings.algorithm)

            app = main.create_app()
            transport = ASGITransport(app=app)

            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                response = await client.get(
                    "/api/projects/search/by-name",
                    params={"name": "武侠"},
                    headers={"Authorization": f"Bearer {token}"},
                )

            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]["name"] == "武侠小说"
        finally:
            await database.drop_db_and_tables()
            await database.engine.dispose()

    @pytest.mark.anyio
    async def test_list_project_members(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        """验证获取项目成员列表 API。"""
        self.set_env(
            monkeypatch,
            {
                "DB_ENGINE": "sqlite",
                "DB_DRIVER": "aiosqlite",
                "DB_SQLITE_PATH": str(tmp_path / "router_members.db"),
            },
        )

        config, database, _, _, _, _, main, _ = self.reload_modules(
            config_module,
            database_module,
            jwt_tools_module,
            project_router_module,
            user_router_module,
            api_module,
            main_module,
            common_middleware_module,
        )

        self._patch_jwt(monkeypatch, config.settings.secret_key, config.settings.algorithm)

        await database.create_db_and_tables()
        try:
            user = await self._setup_user(database, "owner1")
            member_user = await self._setup_user(database, "member1")

            async with database.async_session_maker() as session:
                project = await project_service_module.create_project(session, user.public_id, ProjectCreate(name="成员列表"))
                await project_service_module.add_project_member(
                    session,
                    project.public_id,
                    member_user.public_id,
                    ProjectMemberRole.EDITOR,
                    user.public_id,
                )

            token = self._make_token(user.public_id, user.username, config.settings.secret_key, config.settings.algorithm)

            app = main.create_app()
            transport = ASGITransport(app=app)

            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                response = await client.get(
                    f"/api/projects/{project.public_id}/members",
                    headers={"Authorization": f"Bearer {token}"},
                )

            assert response.status_code == 200
            data = response.json()
            assert len(data) == 2
            roles = {m["role"] for m in data}
            assert roles == {"owner", "editor"}
        finally:
            await database.drop_db_and_tables()
            await database.engine.dispose()

    @pytest.mark.anyio
    async def test_add_project_member_via_router(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        """验证通过 API 新增项目成员。"""
        self.set_env(
            monkeypatch,
            {
                "DB_ENGINE": "sqlite",
                "DB_DRIVER": "aiosqlite",
                "DB_SQLITE_PATH": str(tmp_path / "router_add_member.db"),
            },
        )

        config, database, _, _, _, _, main, _ = self.reload_modules(
            config_module,
            database_module,
            jwt_tools_module,
            project_router_module,
            user_router_module,
            api_module,
            main_module,
            common_middleware_module,
        )

        self._patch_jwt(monkeypatch, config.settings.secret_key, config.settings.algorithm)

        await database.create_db_and_tables()
        try:
            owner = await self._setup_user(database, "owner1")
            new_member = await self._setup_user(database, "newmember")

            async with database.async_session_maker() as session:
                project = await project_service_module.create_project(session, owner.public_id, ProjectCreate(name="添加成员"))

            token = self._make_token(owner.public_id, owner.username, config.settings.secret_key, config.settings.algorithm)

            app = main.create_app()
            transport = ASGITransport(app=app)

            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                response = await client.post(
                    f"/api/projects/{project.public_id}/members",
                    params={
                        "user_public_id": new_member.public_id,
                        "role": "editor",
                    },
                    headers={"Authorization": f"Bearer {token}"},
                )

            assert response.status_code == 201
            data = response.json()
            assert data["user_public_id"] == new_member.public_id
            assert data["role"] == "editor"
        finally:
            await database.drop_db_and_tables()
            await database.engine.dispose()

    @pytest.mark.anyio
    async def test_update_project_member_role_via_router(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        """验证通过 API 更新项目成员角色。"""
        self.set_env(
            monkeypatch,
            {
                "DB_ENGINE": "sqlite",
                "DB_DRIVER": "aiosqlite",
                "DB_SQLITE_PATH": str(tmp_path / "router_update_role.db"),
            },
        )

        config, database, _, _, _, _, main, _ = self.reload_modules(
            config_module,
            database_module,
            jwt_tools_module,
            project_router_module,
            user_router_module,
            api_module,
            main_module,
            common_middleware_module,
        )

        self._patch_jwt(monkeypatch, config.settings.secret_key, config.settings.algorithm)

        await database.create_db_and_tables()
        try:
            owner = await self._setup_user(database, "owner1")
            member = await self._setup_user(database, "member1")

            async with database.async_session_maker() as session:
                project = await project_service_module.create_project(session, owner.public_id, ProjectCreate(name="角色更新"))
                await project_service_module.add_project_member(
                    session,
                    project.public_id,
                    member.public_id,
                    ProjectMemberRole.VIEWER,
                    owner.public_id,
                )

            token = self._make_token(owner.public_id, owner.username, config.settings.secret_key, config.settings.algorithm)

            app = main.create_app()
            transport = ASGITransport(app=app)

            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                response = await client.patch(
                    f"/api/projects/{project.public_id}/members/{member.public_id}",
                    params={"role": "admin"},
                    headers={"Authorization": f"Bearer {token}"},
                )

            assert response.status_code == 200
            data = response.json()
            assert data["role"] == "admin"
        finally:
            await database.drop_db_and_tables()
            await database.engine.dispose()

    @pytest.mark.anyio
    async def test_remove_project_member_via_router(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        """验证通过 API 移除项目成员。"""
        self.set_env(
            monkeypatch,
            {
                "DB_ENGINE": "sqlite",
                "DB_DRIVER": "aiosqlite",
                "DB_SQLITE_PATH": str(tmp_path / "router_remove_member.db"),
            },
        )

        config, database, _, _, _, _, main, _ = self.reload_modules(
            config_module,
            database_module,
            jwt_tools_module,
            project_router_module,
            user_router_module,
            api_module,
            main_module,
            common_middleware_module,
        )

        self._patch_jwt(monkeypatch, config.settings.secret_key, config.settings.algorithm)

        await database.create_db_and_tables()
        try:
            owner = await self._setup_user(database, "owner1")
            member = await self._setup_user(database, "member1")

            async with database.async_session_maker() as session:
                project = await project_service_module.create_project(session, owner.public_id, ProjectCreate(name="移除成员"))
                await project_service_module.add_project_member(
                    session,
                    project.public_id,
                    member.public_id,
                    ProjectMemberRole.VIEWER,
                    owner.public_id,
                )

            token = self._make_token(owner.public_id, owner.username, config.settings.secret_key, config.settings.algorithm)

            app = main.create_app()
            transport = ASGITransport(app=app)

            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                response = await client.delete(
                    f"/api/projects/{project.public_id}/members/{member.public_id}",
                    headers={"Authorization": f"Bearer {token}"},
                )

            assert response.status_code == 204

            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                list_resp = await client.get(
                    f"/api/projects/{project.public_id}/members",
                    headers={"Authorization": f"Bearer {token}"},
                )
            members = list_resp.json()
            assert len(members) == 1
        finally:
            await database.drop_db_and_tables()
            await database.engine.dispose()

    @pytest.mark.anyio
    async def test_invite_project_member_via_router(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        """验证通过 API 邀请项目成员。"""
        self.set_env(
            monkeypatch,
            {
                "DB_ENGINE": "sqlite",
                "DB_DRIVER": "aiosqlite",
                "DB_SQLITE_PATH": str(tmp_path / "router_invite.db"),
            },
        )

        config, database, _, _, _, _, main, _ = self.reload_modules(
            config_module,
            database_module,
            jwt_tools_module,
            project_router_module,
            user_router_module,
            api_module,
            main_module,
            common_middleware_module,
        )

        self._patch_jwt(monkeypatch, config.settings.secret_key, config.settings.algorithm)

        await database.create_db_and_tables()
        try:
            owner = await self._setup_user(database, "owner1")
            invitee = await self._setup_user(database, "invitee")

            async with database.async_session_maker() as session:
                project = await project_service_module.create_project(session, owner.public_id, ProjectCreate(name="邀请成员"))

            token = self._make_token(owner.public_id, owner.username, config.settings.secret_key, config.settings.algorithm)

            app = main.create_app()
            transport = ASGITransport(app=app)

            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                response = await client.post(
                    f"/api/projects/{project.public_id}/members/invitations",
                    json={
                        "user_public_id": invitee.public_id,
                        "role": "manager",
                    },
                    headers={"Authorization": f"Bearer {token}"},
                )

            assert response.status_code == 201
            data = response.json()
            assert data["role"] == "manager"
            assert data["user_public_id"] == invitee.public_id
        finally:
            await database.drop_db_and_tables()
            await database.engine.dispose()

    @pytest.mark.anyio
    async def test_search_project_member_candidates_via_router(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        """验证通过 API 搜索可邀请成员。"""
        self.set_env(
            monkeypatch,
            {
                "DB_ENGINE": "sqlite",
                "DB_DRIVER": "aiosqlite",
                "DB_SQLITE_PATH": str(tmp_path / "router_candidates.db"),
            },
        )

        config, database, _, _, _, _, main, _ = self.reload_modules(
            config_module,
            database_module,
            jwt_tools_module,
            project_router_module,
            user_router_module,
            api_module,
            main_module,
            common_middleware_module,
        )

        self._patch_jwt(monkeypatch, config.settings.secret_key, config.settings.algorithm)

        await database.create_db_and_tables()
        try:
            owner = await self._setup_user(database, "owner1")
            await self._setup_user(database, "alice")
            await self._setup_user(database, "bob")

            async with database.async_session_maker() as session:
                project = await project_service_module.create_project(session, owner.public_id, ProjectCreate(name="候选测试"))

            token = self._make_token(owner.public_id, owner.username, config.settings.secret_key, config.settings.algorithm)

            app = main.create_app()
            transport = ASGITransport(app=app)

            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                response = await client.get(
                    f"/api/projects/{project.public_id}/members/candidates",
                    params={"keyword": "ali"},
                    headers={"Authorization": f"Bearer {token}"},
                )

            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]["username"] == "alice"
        finally:
            await database.drop_db_and_tables()
            await database.engine.dispose()

    @pytest.mark.anyio
    async def test_search_projects_by_member_via_router(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        """验证通过 API 按成员搜索项目。"""
        self.set_env(
            monkeypatch,
            {
                "DB_ENGINE": "sqlite",
                "DB_DRIVER": "aiosqlite",
                "DB_SQLITE_PATH": str(tmp_path / "router_search_member.db"),
            },
        )

        config, database, _, _, _, _, main, _ = self.reload_modules(
            config_module,
            database_module,
            jwt_tools_module,
            project_router_module,
            user_router_module,
            api_module,
            main_module,
            common_middleware_module,
        )

        self._patch_jwt(monkeypatch, config.settings.secret_key, config.settings.algorithm)

        await database.create_db_and_tables()
        try:
            owner = await self._setup_user(database, "owner1")
            member = await self._setup_user(database, "member1")

            async with database.async_session_maker() as session:
                p1 = await project_service_module.create_project(session, owner.public_id, ProjectCreate(name="O的项目"))
                # 将 member 加入 p1，使 member 同时是 p1 的成员和 p2 的 owner
                await project_service_module.add_project_member(
                    session,
                    p1.public_id,
                    member.public_id,
                    ProjectMemberRole.EDITOR,
                    owner.public_id,
                )
                p2 = await project_service_module.create_project(session, member.public_id, ProjectCreate(name="M的项目"))
                # 将 owner 加入 p2，使 owner 有权限查看 p2
                await project_service_module.add_project_member(
                    session,
                    p2.public_id,
                    owner.public_id,
                    ProjectMemberRole.EDITOR,
                    member.public_id,
                )

            token = self._make_token(owner.public_id, owner.username, config.settings.secret_key, config.settings.algorithm)

            app = main.create_app()
            transport = ASGITransport(app=app)

            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                response = await client.get(
                    "/api/projects/search/by-member",
                    params={"member_public_id": member.public_id},
                    headers={"Authorization": f"Bearer {token}"},
                )

            assert response.status_code == 200
            data = response.json()
            # owner 可访问 2 个项目：O的项目（owner_id=owner, owner 是成员）和 M的项目（owner 是其成员）
            assert len(data) == 2
        finally:
            await database.drop_db_and_tables()
            await database.engine.dispose()

    @pytest.mark.anyio
    async def test_non_owner_cannot_access_others_project(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        """验证非成员用户无法访问他人项目，返回 403。"""
        self.set_env(
            monkeypatch,
            {
                "DB_ENGINE": "sqlite",
                "DB_DRIVER": "aiosqlite",
                "DB_SQLITE_PATH": str(tmp_path / "router_403.db"),
            },
        )

        config, database, _, _, _, _, main, _ = self.reload_modules(
            config_module,
            database_module,
            jwt_tools_module,
            project_router_module,
            user_router_module,
            api_module,
            main_module,
            common_middleware_module,
        )

        self._patch_jwt(monkeypatch, config.settings.secret_key, config.settings.algorithm)

        await database.create_db_and_tables()
        try:
            owner = await self._setup_user(database, "owner1")
            other = await self._setup_user(database, "other")

            async with database.async_session_maker() as session:
                project = await project_service_module.create_project(session, owner.public_id, ProjectCreate(name="私有项目"))

            token = self._make_token(other.public_id, other.username, config.settings.secret_key, config.settings.algorithm)

            app = main.create_app()
            transport = ASGITransport(app=app)

            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                response = await client.get(
                    f"/api/projects/{project.public_id}",
                    headers={"Authorization": f"Bearer {token}"},
                )

            assert response.status_code == 403
        finally:
            await database.drop_db_and_tables()
            await database.engine.dispose()


# ---- 测试辅助函数 ----

async def _noop_cache_token(*args, **kwargs) -> None:
    """绕过 Redis 的 cache_token 空操作。"""
    return None


def _no_redis_decode_token(secret_key: str, algorithm: str):
    """返回一个不依赖 Redis 的 decode_token 实现。"""

    async def _decode(token: str) -> dict:
        import jwt as _jwt

        payload = _jwt.decode(token, secret_key, algorithms=[algorithm])
        return payload

    return _decode
