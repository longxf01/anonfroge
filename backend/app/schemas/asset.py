from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.screenwriting import to_camel


READ_SCHEMA_CONFIG = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=to_camel)
WRITE_SCHEMA_CONFIG = ConfigDict(populate_by_name=True, alias_generator=to_camel)


class AssetRead(BaseModel):
    """资产响应。"""

    model_config = READ_SCHEMA_CONFIG

    public_id: str
    asset_type: str
    name: str = ""
    keyword: str = ""
    colors: str = ""
    summary: str = ""
    description: str = ""
    details: str = "{}"
    accessories: str = "{}"
    status: str = "draft"
    main_asset: bool = False
    variant_label: str = ""
    created_at: datetime
    updated_at: datetime


class AssetEpisodeBrief(BaseModel):
    """资产关联分集摘要。"""

    model_config = READ_SCHEMA_CONFIG

    episode_id: str
    episode_name: str = ""


class AssetDetailRead(AssetRead):
    """资产详情响应。"""

    episode_items: list[AssetEpisodeBrief] = Field(default_factory=list)


class AssetExtractRequest(BaseModel):
    """从剧本正文抽取资产的请求。"""

    model_config = WRITE_SCHEMA_CONFIG

    model_id: str = Field(min_length=1, max_length=120, description="抽取所用文本模型 ID。")
    episode_public_ids: list[str] = Field(default_factory=list, description="指定分集公开 ID；留空则抽取最新剧本全集。")


class AssetAssociationRequest(BaseModel):
    """设置分集关联资产的请求。"""

    model_config = WRITE_SCHEMA_CONFIG

    episode_public_id: str = Field(min_length=1, description="分集公开 ID。")
    asset_public_ids: list[str] = Field(default_factory=list, description="关联的资产公开 ID 列表。")


class AssetAssociationResult(BaseModel):
    """分集关联资产结果。"""

    model_config = READ_SCHEMA_CONFIG

    affected: int = 0
    assets: list[AssetRead] = Field(default_factory=list)


class AssetExtractResult(BaseModel):
    """资产抽取结果。"""

    model_config = READ_SCHEMA_CONFIG

    created: int = 0
    updated: int = 0
    assets: list[AssetRead] = Field(default_factory=list)


class AssetBatchResult(BaseModel):
    """批量操作资产结果。"""

    model_config = READ_SCHEMA_CONFIG

    affected: int = 0
    assets: list[AssetRead] = Field(default_factory=list)
