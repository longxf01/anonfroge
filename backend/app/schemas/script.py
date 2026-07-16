from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.screenwriting import to_camel


READ_SCHEMA_CONFIG = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=to_camel)
WRITE_SCHEMA_CONFIG = ConfigDict(populate_by_name=True, alias_generator=to_camel)


class ScriptSyncPayload(BaseModel):
    """从剧本创作会话同步到剧本管理的请求。"""

    model_config = WRITE_SCHEMA_CONFIG

    title: str = Field(default="", max_length=200)


class ScriptSceneRead(BaseModel):
    """剧本分集的单场结构。"""

    model_config = WRITE_SCHEMA_CONFIG

    number: str = ""
    title: str = ""
    location: str = ""
    day_night: str = ""
    interior_exterior: str = ""


class ScriptEpisodeRead(BaseModel):
    """剧本分集。"""

    model_config = READ_SCHEMA_CONFIG

    public_id: str
    episode_index: int
    title: str = ""
    summary: str = ""
    body: str = ""
    scenes: list[ScriptSceneRead] = Field(default_factory=list)
    version: int = 1
    is_locked: bool = False

    @classmethod
    def from_model(cls, episode: Any) -> "ScriptEpisodeRead":
        try:
            raw_scenes = json.loads(episode.scenes or "[]")
        except (TypeError, ValueError):
            raw_scenes = []
        return cls(
            public_id=episode.public_id,
            episode_index=episode.episode_index,
            title=episode.title,
            summary=episode.summary,
            body=episode.body,
            scenes=[ScriptSceneRead.model_validate(scene) for scene in raw_scenes if isinstance(scene, dict)],
            version=episode.version,
            is_locked=bool(episode.is_locked),
        )


class ScriptPlanSummary(BaseModel):
    """剧本计划列表项。"""

    model_config = READ_SCHEMA_CONFIG

    public_id: str
    title: str = ""
    total_episodes: str = ""
    episode_duration: str = ""
    status: str = "synced"
    updated_at: datetime


class ScriptPlanDetail(BaseModel):
    """剧本计划详情（含分集）。"""

    model_config = READ_SCHEMA_CONFIG

    public_id: str
    title: str = ""
    total_episodes: str = ""
    episode_duration: str = ""
    source_range: str = ""
    platform_spec: str = ""
    style: str = ""
    paywall: str = ""
    status: str = "synced"
    updated_at: datetime
    episodes: list[ScriptEpisodeRead] = Field(default_factory=list)