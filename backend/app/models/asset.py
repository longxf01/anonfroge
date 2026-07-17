from __future__ import annotations
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Boolean, String, Text, UniqueConstraint
from sqlmodel import Field

from app.models.base import BaseModel


# 资产类型：自动抽取人物、势力、道具、场景。
ASSET_TYPE_ROLE = "role"
ASSET_TYPE_FACTION = "faction"
ASSET_TYPE_PROP = "prop"
ASSET_TYPE_SCENE = "scene"
ASSET_TYPE_LENS = "lens"

# 资产状态：锁定后，后续重新抽取不会覆盖资产描述与关联信息。
ASSET_STATUS_DRAFT = "draft"
ASSET_STATUS_LOCKED = "locked"

# 资产与分集关系来源。
ASSET_EPISODE_SOURCE_EXTRACTION = "extraction"
ASSET_EPISODE_SOURCE_MANUAL = "manual"

# 资产关系类型：source_asset_id 指向 target_asset_id。
ASSET_RELATION_CHILD_OF = "child_of"
ASSET_RELATION_DERIVATIVE_OF = "derivative_of"
ASSET_RELATION_USES = "uses"
ASSET_RELATION_APPEARS_WITH = "appears_with"
ASSET_RELATION_BELONGS_TO = "belongs_to"

# 资产媒体类型与用途。
ASSET_MEDIA_TYPE_IMAGE = "image"
ASSET_MEDIA_TYPE_VIDEO = "video"
ASSET_MEDIA_TYPE_AUDIO = "audio"
ASSET_MEDIA_TYPE_FILE = "file"

ASSET_MEDIA_ROLE_REFERENCE = "reference"
ASSET_MEDIA_ROLE_GENERATED = "generated"
ASSET_MEDIA_ROLE_FINAL = "final"
ASSET_MEDIA_ROLE_PREVIEW = "preview"

# 资产生成类型与状态。
ASSET_GENERATION_TYPE_DESCRIPTION = "description"
ASSET_GENERATION_TYPE_IMAGE = "image"
ASSET_GENERATION_TYPE_VIDEO = "video"
ASSET_GENERATION_TYPE_AUDIO = "audio"

ASSET_GENERATION_STATUS_PENDING = "pending"
ASSET_GENERATION_STATUS_RUNNING = "running"
ASSET_GENERATION_STATUS_SUCCEEDED = "succeeded"
ASSET_GENERATION_STATUS_FAILED = "failed"
ASSET_GENERATION_STATUS_CANCELLED = "cancelled"


class Asset(BaseModel, table=True):
    """剧本制作资产。

    资产从剧本分集正文中抽取，按（项目、用户、类型、名称）唯一归并。
    资产描述字段与 data/skills/asset_extraction.md 输出结构保持一致。
    """

    __tablename__ = "af_asset"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "user_public_id",
            "asset_type",
            "name",
            name="uq_af_asset_project_user_type_name",
        ),
    )

    project_id: int = Field(
        sa_column=Column("project_id", Integer, ForeignKey("af_project.id"), nullable=False, index=True),
        description="资产所属项目内部主键。",
    )
    user_public_id: str = Field(
        sa_column=Column("user_public_id", String(36), nullable=False, index=True),
        description="资产所属用户公开标识。",
    )
    asset_type: str = Field(
        default=ASSET_TYPE_ROLE,
        sa_column=Column(
            "asset_type",
            String(20),
            nullable=False,
            default=ASSET_TYPE_ROLE,
            server_default=ASSET_TYPE_ROLE,
            index=True,
        ),
        description="资产类型：role/faction/prop/scene",
    )
    name: str = Field(
        default="",
        sa_column=Column("name", String(200), nullable=False, default="", server_default=""),
        description="资产名称。",
    )
    keyword: str = Field(
        default="",
        sa_column=Column("keyword", String(500), nullable=False, default="", server_default=""),
        description="资产关键词，来自抽取结果 keyword 字段。",
    )
    colors: str = Field(
        default="",
        sa_column=Column("colors", String(1000), nullable=False, default="", server_default=""),
        description="资产色彩方案，来自抽取结果 colors 字段。",
    )
    summary: str = Field(
        default="",
        sa_column=Column("summary", Text, nullable=False, default="", server_default=""),
        description="资产摘要概述，来自抽取结果 summary 字段。",
    )
    description: str = Field(
        default="",
        sa_column=Column("description", Text, nullable=False, default="", server_default=""),
        description="资产基础整体描述 JSON 字符串，对应抽取结果 description 对象。",
    )
    details: str = Field(
        default="{}",
        sa_column=Column("details", Text, nullable=False, default="{}", server_default="{}"),
        description="资产细节部位拆解 JSON 字符串，对应抽取结果 details 对象。",
    )
    accessories: str = Field(
        default="{}",
        sa_column=Column("accessories", Text, nullable=False, default="{}", server_default="{}"),
        description="资产外观附属元素 JSON 字符串，对应抽取结果 accessories 对象。",
    )
    status: str = Field(
        default=ASSET_STATUS_DRAFT,
        sa_column=Column(
            "status",
            String(20),
            nullable=False,
            default=ASSET_STATUS_DRAFT,
            server_default=ASSET_STATUS_DRAFT,
            index=True,
        ),
        description="资产状态：draft/locked。",
    )
    main_asset: bool = Field(
        default=False,
        sa_column=Column("main_asset", Boolean, nullable=False, default=0, server_default="0", index=True),
        description="是否为主资产；主资产在列表中优先展示，子资产不参与主资产列表展示。",
    )
    variant_label: str = Field(
        default="",
        sa_column=Column("variant_label", String(100), nullable=False, default="", server_default=""),
        description="子资产变体标签，例如黑衣人、少年状态、受伤状态。",
    )

class AssetRelation(BaseModel, table=True):
    """资产之间的语义关系表。"""

    __tablename__ = "af_asset_relation"
    __table_args__ = (
        UniqueConstraint(
            "source_asset_id",
            "target_asset_id",
            "relation_type",
            name="uq_af_asset_relation_source_target_type",
        ),
    )

    source_asset_id: int = Field(
        sa_column=Column("source_asset_id", Integer, ForeignKey("af_asset.id"), nullable=False, index=True),
        description="关系起点资产内部主键。",
    )

    target_asset_id: int = Field(
        sa_column=Column("target_asset_id", Integer, ForeignKey("af_asset.id"), nullable=False, index=True),
        description="关系终点资产内部主键。",
    )

    relation_type: str = Field(
        default=ASSET_RELATION_APPEARS_WITH,
        sa_column=Column(
            "relation_type",
            String(40),
            nullable=False,
            default=ASSET_RELATION_APPEARS_WITH,
            server_default=ASSET_RELATION_APPEARS_WITH,
            index=True,
        ),
        description="关系类型：child_of/derivative_of/uses/appears_with/belongs_to。",
    )
    relation_label: str = Field(
        default="",
        sa_column=Column("relation_label", String(120), nullable=False, default="", server_default=""),
        description="面向展示的关系标签。",
    )

class AssetEpisode(BaseModel, table=True):
    """资产与剧本分集的关联表。"""

    __tablename__ = "af_asset_episode"
    __table_args__ = (
        UniqueConstraint("asset_id", "episode_id", name="uq_af_asset_episode_asset_episode"),
    )

    project_id: int = Field(
        sa_column=Column("project_id", Integer, ForeignKey("af_project.id"), nullable=False, index=True),
        description="资产所属项目内部主键，冗余保存以便按项目查询。",
    )
    user_public_id: str = Field(
        sa_column=Column("user_public_id", String(36), nullable=False, index=True),
        description="资产所属用户公开标识，冗余保存以便按用户隔离。",
    )
    asset_id: int = Field(
        sa_column=Column("asset_id", Integer, ForeignKey("af_asset.id"), nullable=False, index=True),
        description="资产内部主键。",
    )
    episode_id: int = Field(
        sa_column=Column("episode_id", Integer, ForeignKey("af_script_episode.id"), nullable=False, index=True),
        description="剧本分集内部主键。",
    )
    episode_index: int = Field(
        default=0,
        sa_column=Column("episode_index", Integer, nullable=False, default=0, server_default="0", index=True),
        description="分集序号快照，用于快速过滤和展示。",
    )
    source: str = Field(
        default=ASSET_EPISODE_SOURCE_EXTRACTION,
        sa_column=Column(
            "source",
            String(40),
            nullable=False,
            default=ASSET_EPISODE_SOURCE_EXTRACTION,
            server_default=ASSET_EPISODE_SOURCE_EXTRACTION,
            index=True,
        ),
        description="关联来源：extraction/manual。",
    )

class AssetVersion(BaseModel, table=True):
    """资产版本快照表。"""

    __tablename__ = "af_asset_version"
    __table_args__ = (
        UniqueConstraint("asset_id", "version", name="uq_af_asset_version_asset_version"),
    )

    project_id: int = Field(
        sa_column=Column("project_id", Integer, ForeignKey("af_project.id"), nullable=False, index=True),
        description="资产所属项目内部主键，冗余保存以便按项目查询。",
    )
    user_public_id: str = Field(
        sa_column=Column("user_public_id", String(36), nullable=False, index=True),
        description="资产所属用户公开标识，冗余保存以便按用户隔离。",
    )
    asset_id: int = Field(
        sa_column=Column("asset_id", Integer, ForeignKey("af_asset.id"), nullable=False, index=True),
        description="资产内部主键。",
    )
    version: int = Field(
        default=1,
        sa_column=Column("version", Integer, nullable=False, default=1, server_default="1"),
        description="资产版本号，同一资产内递增。",
    )
    snapshot: str = Field(
        default="{}",
        sa_column=Column("snapshot", Text, nullable=False, default="{}", server_default="{}"),
        description="资产字段与关联信息快照 JSON 字符串。",
    )
    change_note: str = Field(
        default="",
        sa_column=Column("change_note", Text, nullable=False, default="", server_default=""),
        description="版本变更说明。",
    )
    created_by: str = Field(
        default="",
        sa_column=Column("created_by", String(36), nullable=False, default="", server_default="", index=True),
        description="创建该版本的用户公开标识；系统生成时为空。",
    )

class AssetMedia(BaseModel, table=True):
    """资产媒体资源表。"""

    __tablename__ = "af_asset_media"

    project_id: int = Field(
        sa_column=Column("project_id", Integer, ForeignKey("af_project.id"), nullable=False, index=True),
        description="资产所属项目内部主键，冗余保存以便按项目查询。",
    )
    user_public_id: str = Field(
        sa_column=Column("user_public_id", String(36), nullable=False, index=True),
        description="资产所属用户公开标识，冗余保存以便按用户隔离。",
    )
    asset_id: int = Field(
        sa_column=Column("asset_id", Integer, ForeignKey("af_asset.id"), nullable=False, index=True),
        description="资产内部主键。",
    )
    media_type: str = Field(
        default=ASSET_MEDIA_TYPE_IMAGE,
        sa_column=Column(
            "media_type",
            String(20),
            nullable=False,
            default=ASSET_MEDIA_TYPE_IMAGE,
            server_default=ASSET_MEDIA_TYPE_IMAGE,
            index=True,
        ),
        description="媒体类型：image/video/audio/file。",
    )
    media_role: str = Field(
        default=ASSET_MEDIA_ROLE_REFERENCE,
        sa_column=Column(
            "media_role",
            String(40),
            nullable=False,
            default=ASSET_MEDIA_ROLE_REFERENCE,
            server_default=ASSET_MEDIA_ROLE_REFERENCE,
            index=True,
        ),
        description="媒体用途：reference/generated/final/preview。",
    )
    url: str = Field(
        default="",
        sa_column=Column("url", String(2000), nullable=False, default="", server_default=""),
        description="媒体可访问 URL。",
    )
    storage_key: str = Field(
        default="",
        sa_column=Column("storage_key", String(1000), nullable=False, default="", server_default="", index=True),
        description="对象存储键或本地存储相对路径。",
    )
    mime_type: str = Field(
        default="",
        sa_column=Column("mime_type", String(120), nullable=False, default="", server_default=""),
        description="媒体 MIME 类型。",
    )
    width: int = Field(
        default=0,
        sa_column=Column("width", Integer, nullable=False, default=0, server_default="0"),
        description="图像或视频宽度，未知时为 0。",
    )
    height: int = Field(
        default=0,
        sa_column=Column("height", Integer, nullable=False, default=0, server_default="0"),
        description="图像或视频高度，未知时为 0。",
    )
    duration_ms: int = Field(
        default=0,
        sa_column=Column("duration_ms", Integer, nullable=False, default=0, server_default="0"),
        description="音视频时长毫秒，未知时为 0。",
    )
    prompt: str = Field(
        default="",
        sa_column=Column("prompt", Text, nullable=False, default="", server_default=""),
        description="生成该媒体时使用的提示词；非生成媒体为空。",
    )
    generation_public_id: str = Field(
        default="",
        sa_column=Column("generation_public_id", String(36), nullable=False, default="", server_default="", index=True),
        description="关联的资产生成记录公开标识。",
    )
    extra_data: str = Field(
        default="{}",
        sa_column=Column("extra_data", Text, nullable=False, default="{}", server_default="{}"),
        description="媒体扩展信息 JSON 字符串。",
    )

class AssetGeneration(BaseModel, table=True):
    """资产生成任务与结果记录表。"""

    __tablename__ = "af_asset_generation"

    project_id: int = Field(
        sa_column=Column("project_id", Integer, ForeignKey("af_project.id"), nullable=False, index=True),
        description="资产所属项目内部主键，冗余保存以便按项目查询。",
    )
    user_public_id: str = Field(
        sa_column=Column("user_public_id", String(36), nullable=False, index=True),
        description="资产所属用户公开标识，冗余保存以便按用户隔离。",
    )
    asset_id: int = Field(
        sa_column=Column("asset_id", Integer, ForeignKey("af_asset.id"), nullable=False, index=True),
        description="资产内部主键。",
    )
    generation_type: str = Field(
        default=ASSET_GENERATION_TYPE_IMAGE,
        sa_column=Column(
            "generation_type",
            String(40),
            nullable=False,
            default=ASSET_GENERATION_TYPE_IMAGE,
            server_default=ASSET_GENERATION_TYPE_IMAGE,
            index=True,
        ),
        description="生成类型：description/image/video/audio。",
    )
    provider: str = Field(
        default="",
        sa_column=Column("provider", String(80), nullable=False, default="", server_default="", index=True),
        description="生成服务提供方。",
    )
    model_id: str = Field(
        default="",
        sa_column=Column("model_id", String(120), nullable=False, default="", server_default="", index=True),
        description="生成模型标识。",
    )
    prompt: str = Field(
        default="",
        sa_column=Column("prompt", Text, nullable=False, default="", server_default=""),
        description="正向提示词。",
    )
    negative_prompt: str = Field(
        default="",
        sa_column=Column("negative_prompt", Text, nullable=False, default="", server_default=""),
        description="负向提示词。",
    )
    parameters: str = Field(
        default="{}",
        sa_column=Column("parameters", Text, nullable=False, default="{}", server_default="{}"),
        description="生成参数 JSON 字符串。",
    )
    status: str = Field(
        default=ASSET_GENERATION_STATUS_PENDING,
        sa_column=Column(
            "status",
            String(20),
            nullable=False,
            default=ASSET_GENERATION_STATUS_PENDING,
            server_default=ASSET_GENERATION_STATUS_PENDING,
            index=True,
        ),
        description="生成状态：pending/running/succeeded/failed/cancelled。",
    )
    task_job_public_id: str = Field(
        default="",
        sa_column=Column("task_job_public_id", String(36), nullable=False, default="", server_default="", index=True),
        description="关联异步任务公开标识。",
    )
    task_item_public_id: str = Field(
        default="",
        sa_column=Column("task_item_public_id", String(36), nullable=False, default="", server_default="", index=True),
        description="关联异步任务子项公开标识。",
    )
    output: str = Field(
        default="{}",
        sa_column=Column("output", Text, nullable=False, default="{}", server_default="{}"),
        description="生成输出 JSON 字符串，可记录媒体 URL、文本结果或提供方原始响应摘要。",
    )
    error_message: str = Field(
        default="",
        sa_column=Column("error_message", Text, nullable=False, default="", server_default=""),
        description="生成失败原因。",
    )
    started_at: datetime | None = Field(
        default=None,
        sa_column=Column("started_at", DateTime(timezone=True), nullable=True),
        description="生成开始时间。",
    )
    completed_at: datetime | None = Field(
        default=None,
        sa_column=Column("completed_at", DateTime(timezone=True), nullable=True),
        description="生成完成时间。",
    )
