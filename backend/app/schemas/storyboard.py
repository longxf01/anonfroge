from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.screenwriting import to_camel


READ_SCHEMA_CONFIG = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=to_camel)
WRITE_SCHEMA_CONFIG = ConfigDict(populate_by_name=True, alias_generator=to_camel)


class StoryboardGenerateRequest(BaseModel):
    """Request to generate storyboard shots from script episodes."""

    model_config = WRITE_SCHEMA_CONFIG

    model_id: str = Field(min_length=1, max_length=120, description="Text model id.")
    episode_public_ids: list[str] = Field(default_factory=list, description="Target episode ids; empty means latest plan.")
    art_style: str = Field(default="", max_length=120, description="Optional visual style key.")
    director_style: str = Field(default="", max_length=120, description="Optional director style key.")


class StoryboardShotUpdate(BaseModel):
    """Patch fields for one storyboard shot."""

    model_config = WRITE_SCHEMA_CONFIG

    scene_number: str | None = Field(default=None, max_length=40)
    shot_size: str | None = Field(default=None, max_length=40)
    camera: str | None = Field(default=None, max_length=120)
    action: str | None = None
    dialogue: str | None = None
    duration_seconds: int | None = Field(default=None, ge=0)
    asset_public_ids: str | None = Field(default=None, max_length=400)
    asset_names: str | None = Field(default=None, max_length=400)
    art_style_key: str | None = Field(default=None, max_length=120)
    director_style_key: str | None = Field(default=None, max_length=120)
    model_id: str | None = Field(default=None, max_length=120)
    prompt: str | None = None
    negative_prompt: str | None = None
    reference_media_public_id: str | None = Field(default=None, max_length=36)
    seed: str | None = Field(default=None, max_length=60)


class StoryboardShotRead(BaseModel):
    """Storyboard shot response."""

    model_config = READ_SCHEMA_CONFIG

    public_id: str
    episode_public_id: str = ""
    episode_index: int = 0
    scene_number: str = ""
    shot_index: int = 0
    shot_size: str = ""
    camera: str = ""
    action: str = ""
    dialogue: str = ""
    duration_seconds: int = 0
    asset_public_ids: str = ""
    asset_names: str = ""
    art_style_key: str = ""
    director_style_key: str = ""
    model_id: str = ""
    prompt: str = ""
    negative_prompt: str = ""
    reference_media_public_id: str = ""
    seed: str = ""
    status: str = "draft"
    created_at: datetime
    updated_at: datetime


class StoryboardGenerateResult(BaseModel):
    """Synchronous generation result."""

    model_config = READ_SCHEMA_CONFIG

    created: int = 0
    updated: int = 0
    shots: list[StoryboardShotRead] = Field(default_factory=list)