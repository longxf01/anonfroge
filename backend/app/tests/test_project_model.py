from __future__ import annotations

import pytest

from app.models.project import (
    Project,
    ProjectMember,
    ProjectMemberRole,
    ProjectVideoMode,
    enum_values,
)


class TestProjectEnum:
    """项目枚举类型测试。"""

    def test_project_video_mode_values(self) -> None:
        """验证视频生成模式枚举值。"""
        assert ProjectVideoMode.TEXT.value == "text"
        assert ProjectVideoMode.SINGLE_IMAGE.value == "singleImage"
        assert ProjectVideoMode.START_END_REQUIRED.value == "startEndRequired"
        assert ProjectVideoMode.END_FRAME_OPTIONAL.value == "endFrameOptional"
        assert ProjectVideoMode.START_FRAME_OPTIONAL.value == "startFrameOptional"

    def test_project_member_role_values(self) -> None:
        """验证成员角色枚举值。"""
        assert ProjectMemberRole.OWNER.value == "owner"
        assert ProjectMemberRole.ADMIN.value == "admin"
        assert ProjectMemberRole.MANAGER.value == "manager"
        assert ProjectMemberRole.EDITOR.value == "editor"
        assert ProjectMemberRole.VIEWER.value == "viewer"

    def test_enum_values_returns_value_list(self) -> None:
        """验证 enum_values 返回枚举值列表。"""
        assert set(enum_values(ProjectMemberRole)) == {"owner", "admin", "manager", "editor", "viewer"}
        assert set(enum_values(ProjectVideoMode)) == {
            "text",
            "singleImage",
            "startEndRequired",
            "endFrameOptional",
            "startFrameOptional",
        }


class TestProjectModel:
    """项目模型测试。"""

    @pytest.mark.anyio
    async def test_project_defaults(self) -> None:
        """验证项目模型字段默认值。"""
        project = Project(name="测试项目", owner_id="user-001")

        assert project.name == "测试项目"
        assert project.intro == ""
        assert project.project_type == "novel_to_video"
        assert project.content_type == "novel"
        assert project.art_style == "3D_chinese_traditional"
        assert project.director_manual == ""
        assert project.video_ratio == "9:16"
        assert project.image_model == ""
        assert project.video_model == ""
        assert project.image_quality == "standard"
        assert project.mode == ProjectVideoMode.TEXT
        assert project.owner_id == "user-001"
        assert project.public_id is not None
        assert len(project.public_id) == 36
        assert project.sort_order == 0

    @pytest.mark.anyio
    async def test_project_disable_enable_flow(self) -> None:
        """验证项目禁用/启用流程。"""
        project = Project(name="测试项目", owner_id="user-001")

        assert project.is_active is True
        assert project.is_disabled is False
        assert project.disabled_at is None

        await project.disable()
        assert project.disabled_at is not None
        assert project.is_disabled is True
        assert project.is_active is False

        await project.enable()
        assert project.disabled_at is None
        assert project.is_disabled is False
        assert project.is_active is True


class TestProjectMemberModel:
    """项目成员模型测试。"""

    @pytest.mark.anyio
    async def test_project_member_defaults(self) -> None:
        """验证项目成员默认角色和创建时间。"""
        member = ProjectMember(project_id=1, user_public_id="user-001")

        assert member.project_id == 1
        assert member.user_public_id == "user-001"
        assert member.role == ProjectMemberRole.VIEWER
        assert member.joined_at is not None

    @pytest.mark.anyio
    async def test_project_member_custom_role(self) -> None:
        """验证自定义角色创建。"""
        member = ProjectMember(
            project_id=1,
            user_public_id="user-001",
            role=ProjectMemberRole.OWNER,
        )
        assert member.role == ProjectMemberRole.OWNER
