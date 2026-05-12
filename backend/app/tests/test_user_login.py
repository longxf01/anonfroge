from __future__ import annotations

from httpx import ASGITransport, AsyncClient
import pytest

from app import main as main_module
from app.core import config as config_module
from app.core import database as database_module
from app.models.user import User
from app.routers import api as api_module
from app.routers import user as user_router_module
from app.tests.base import EnvTestBase
from app.utils import jwt_tools as jwt_tools_module
from app.utils.string_tools import hash_password
from app.utils.time_tools import utc_now


class TestUserLogin(EnvTestBase):
    """用户登录接口测试。"""

    @pytest.mark.anyio
    async def test_login_success_returns_tokens_and_user_info(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        """正常登录：正确的用户名和密码应返回 token 和用户信息。"""
        self.set_env(
            monkeypatch,
            {
                "DB_ENGINE": "sqlite",
                "DB_DRIVER": "aiosqlite",
                "DB_SQLITE_PATH": str(tmp_path / "login.db"),
            },
        )

        config, database, jwt_tools, _, _, main = self.reload_modules(
            config_module,
            database_module,
            jwt_tools_module,
            user_router_module,
            api_module,
            main_module,
        )

        # 将 Redis 缓存操作替换为空操作
        async def _noop_cache_token(*args, **kwargs) -> None:
            return None

        monkeypatch.setattr(jwt_tools, "cache_token", _noop_cache_token)

        await database.create_db_and_tables()
        try:
            # 在数据库中创建一个测试用户
            now = utc_now()
            async with database.async_session_maker() as session:
                user = User(
                    username="testuser",
                    nickname="Test User",
                    password_hash=hash_password("password123"),
                    created_at=now,
                    updated_at=now,
                )
                session.add(user)
                await session.commit()
                await session.refresh(user)

            app = main.create_app()
            transport = ASGITransport(app=app)

            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                response = await client.post(
                    "/api/users/login",
                    json={
                        "username": "testuser",
                        "password": "password123",
                    },
                )

            assert response.status_code == 200
            data = response.json()
            assert "access_token" in data
            assert "refresh_token" in data
            assert data["token_type"] == "bearer"
            assert data["expires_in"] > 0
            assert data["user"]["username"] == "testuser"
            assert data["user"]["nickname"] == "Test User"
            assert data["user"]["public_id"] is not None
        finally:
            await database.drop_db_and_tables()
            await database.engine.dispose()

    @pytest.mark.anyio
    async def test_login_user_not_found_returns_401(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        """用户名不存在时应返回 401。"""
        self.set_env(
            monkeypatch,
            {
                "DB_ENGINE": "sqlite",
                "DB_DRIVER": "aiosqlite",
                "DB_SQLITE_PATH": str(tmp_path / "login_404.db"),
            },
        )

        config, database, _, _, main = self.reload_modules(
            config_module,
            database_module,
            user_router_module,
            api_module,
            main_module,
        )

        await database.create_db_and_tables()
        try:
            app = main.create_app()
            transport = ASGITransport(app=app)

            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                response = await client.post(
                    "/api/users/login",
                    json={
                        "username": "nonexistent",
                        "password": "password123",
                    },
                )

            assert response.status_code == 401
            assert response.json()["detail"] == "用户名或密码错误"
        finally:
            await database.drop_db_and_tables()
            await database.engine.dispose()

    @pytest.mark.anyio
    async def test_login_wrong_password_returns_401(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        """密码错误时应返回 401。"""
        self.set_env(
            monkeypatch,
            {
                "DB_ENGINE": "sqlite",
                "DB_DRIVER": "aiosqlite",
                "DB_SQLITE_PATH": str(tmp_path / "login_pwd.db"),
            },
        )

        config, database, _, _, main = self.reload_modules(
            config_module,
            database_module,
            user_router_module,
            api_module,
            main_module,
        )

        await database.create_db_and_tables()
        try:
            now = utc_now()
            async with database.async_session_maker() as session:
                user = User(
                    username="testuser",
                    password_hash=hash_password("password123"),
                    created_at=now,
                    updated_at=now,
                )
                session.add(user)
                await session.commit()

            app = main.create_app()
            transport = ASGITransport(app=app)

            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                response = await client.post(
                    "/api/users/login",
                    json={
                        "username": "testuser",
                        "password": "wrongpassword",
                    },
                )

            assert response.status_code == 401
            assert response.json()["detail"] == "用户名或密码错误"
        finally:
            await database.drop_db_and_tables()
            await database.engine.dispose()

    @pytest.mark.anyio
    async def test_login_disabled_user_returns_403(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        """被禁用的用户登录时应返回 403。"""
        self.set_env(
            monkeypatch,
            {
                "DB_ENGINE": "sqlite",
                "DB_DRIVER": "aiosqlite",
                "DB_SQLITE_PATH": str(tmp_path / "login_disabled.db"),
            },
        )

        config, database, _, _, main = self.reload_modules(
            config_module,
            database_module,
            user_router_module,
            api_module,
            main_module,
        )

        await database.create_db_and_tables()
        try:
            now = utc_now()
            async with database.async_session_maker() as session:
                user = User(
                    username="disableduser",
                    password_hash=hash_password("password123"),
                    disabled_at=now,
                    created_at=now,
                    updated_at=now,
                )
                session.add(user)
                await session.commit()

            app = main.create_app()
            transport = ASGITransport(app=app)

            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                response = await client.post(
                    "/api/users/login",
                    json={
                        "username": "disableduser",
                        "password": "password123",
                    },
                )

            assert response.status_code == 403
            assert response.json()["detail"] == "用户已被禁用"
        finally:
            await database.drop_db_and_tables()
            await database.engine.dispose()

    @pytest.mark.anyio
    async def test_login_updates_last_login_at(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        """登录成功后应更新用户的最近登录时间。"""
        self.set_env(
            monkeypatch,
            {
                "DB_ENGINE": "sqlite",
                "DB_DRIVER": "aiosqlite",
                "DB_SQLITE_PATH": str(tmp_path / "login_last.db"),
            },
        )

        config, database, jwt_tools, _, _, main = self.reload_modules(
            config_module,
            database_module,
            jwt_tools_module,
            user_router_module,
            api_module,
            main_module,
        )

        async def _noop_cache_token(*args, **kwargs) -> None:
            return None

        monkeypatch.setattr(jwt_tools, "cache_token", _noop_cache_token)

        await database.create_db_and_tables()
        try:
            now = utc_now()
            async with database.async_session_maker() as session:
                user = User(
                    username="testuser",
                    password_hash=hash_password("password123"),
                    created_at=now,
                    updated_at=now,
                )
                session.add(user)
                await session.commit()
                await session.refresh(user)
                assert user.last_login_at is None

            app = main.create_app()
            transport = ASGITransport(app=app)

            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                response = await client.post(
                    "/api/users/login",
                    json={
                        "username": "testuser",
                        "password": "password123",
                    },
                )

            assert response.status_code == 200

            # 验证 last_login_at 已更新
            async with database.async_session_maker() as session:
                from app.services.user import get_user_by_username

                updated_user = await get_user_by_username(session, "testuser")
                assert updated_user is not None
                assert updated_user.last_login_at is not None
        finally:
            await database.drop_db_and_tables()
            await database.engine.dispose()
