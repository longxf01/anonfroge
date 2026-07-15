from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def to_camel(value: str) -> str:
    """将 snake_case 字段名转换为 camelCase。"""
    parts = value.split("_")
    return parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])


SCHEMA_CONFIG = ConfigDict(populate_by_name=True, alias_generator=to_camel)
READ_SCHEMA_CONFIG = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=to_camel)

ScreenwritingActiveTab = Literal["skeleton", "strategy", "script"]
ScreenwritingChatRole = Literal["user", "assistant"]


class ScreenwritingChatTurn(BaseModel):
    """剧本创作对话消息。"""

    model_config = SCHEMA_CONFIG

    role: ScreenwritingChatRole
    content: str = Field(min_length=1, max_length=4000)
    time: str = Field(default="", max_length=32)

    @field_validator("content", "time")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class ScreenwritingChatPayload(BaseModel):
    """剧本创作 Agent 多轮对话请求。"""

    model_config = SCHEMA_CONFIG

    message: str = Field(min_length=1, max_length=4000)
    conversation_id: str = Field(default="", max_length=120)
    active_tab: ScreenwritingActiveTab = "skeleton"
    messages: list[ScreenwritingChatTurn] = Field(default_factory=list)
    reset: bool = False
    client_request_started_at_ms: int | None = Field(default=None, ge=0)

    @field_validator("message", "conversation_id")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class ScreenwritingChatResponse(BaseModel):
    """剧本创作 Agent 聚合响应。"""

    model_config = READ_SCHEMA_CONFIG

    conversation_id: str
    isolation_key: str
    model_id: str
    active_tab: ScreenwritingActiveTab
    content: str
    messages: list[ScreenwritingChatTurn] = Field(default_factory=list)
    runtime: dict[str, Any] = Field(default_factory=dict)


class ScreenwritingRagWarmupResponse(BaseModel):
    """剧本创作 RAG 向量索引预热调度结果。"""

    model_config = READ_SCHEMA_CONFIG

    status: str
    rag_isolation_key: str


class ScreenwritingStreamEvent(BaseModel):
    """剧本创作 Agent 流式事件。"""

    model_config = READ_SCHEMA_CONFIG

    type: str
    content: str = ""
    conversation_id: str
    isolation_key: str
    model_id: str
    active_tab: ScreenwritingActiveTab
    data: dict[str, Any] = Field(default_factory=dict)
