from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.tasks import TaskStatus


READ_SCHEMA_CONFIG = ConfigDict(from_attributes=True)


class TaskItemCreate(BaseModel):
    """创建异步任务子项请求。"""

    item_type: str = Field(default="", max_length=100, description="任务子项类型标识")
    item_key: str | None = Field(default=None, max_length=120, description="任务子项唯一键")
    priority: int = Field(default=0, description="任务子项优先级")
    max_attempts: int = Field(default=3, ge=1, le=100, description="最大尝试次数")
    payload: dict[str, Any] = Field(default_factory=dict, description="任务子项参数")
    scheduled_at: datetime | None = Field(default=None, description="计划调度时间")


class TaskJobCreate(BaseModel):
    """创建异步任务请求。"""

    task_type: str = Field(min_length=1, max_length=100, description="任务类型标识")
    queue_name: str = Field(default="default", min_length=1, max_length=120, description="任务队列名称")
    name: str = Field(default="", max_length=255, description="任务展示名称")
    created_by: str = Field(default="", max_length=36, description="任务创建人的用户公开标识")
    idempotency_key: str = Field(default="", max_length=120, description="幂等键")
    priority: int = Field(default=0, description="任务优先级")
    payload: dict[str, Any] = Field(default_factory=dict, description="任务参数")
    scheduled_at: datetime | None = Field(default=None, description="计划调度时间")
    items: list[TaskItemCreate] = Field(default_factory=list, description="初始任务子项")


class TaskStatusUpdate(BaseModel):
    """更新异步任务状态请求。"""

    status: TaskStatus = Field(description="目标状态")
    result: dict[str, Any] | None = Field(default=None, description="执行结果")
    error_code: str = Field(default="", max_length=100, description="错误码")
    error_message: str = Field(default="", description="错误信息")
    worker_id: str | None = Field(default=None, max_length=120, description="Worker 标识")


class TaskItemRead(BaseModel):
    """异步任务子项响应。"""

    model_config = READ_SCHEMA_CONFIG

    id: int
    public_id: str
    job_id: int
    item_type: str
    item_key: str | None
    status: TaskStatus
    priority: int
    attempt_count: int
    max_attempts: int
    worker_id: str
    payload: dict[str, Any]
    result: dict[str, Any]
    error_code: str
    error_message: str
    scheduled_at: datetime | None
    started_at: datetime | None
    heartbeat_at: datetime | None
    completed_at: datetime | None
    sort_order: int
    created_at: datetime
    updated_at: datetime
    disabled_at: datetime | None


class TaskJobRead(BaseModel):
    """异步任务响应。"""

    model_config = READ_SCHEMA_CONFIG

    id: int
    public_id: str
    task_type: str
    queue_name: str
    name: str
    status: TaskStatus
    created_by: str
    idempotency_key: str
    priority: int
    total_items: int
    completed_items: int
    failed_items: int
    cancelled_items: int
    payload: dict[str, Any]
    result: dict[str, Any]
    error_code: str
    error_message: str
    scheduled_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    sort_order: int
    created_at: datetime
    updated_at: datetime
    disabled_at: datetime | None


class TaskJobDetail(TaskJobRead):
    """异步任务详情响应。"""

    items: list[TaskItemRead] = Field(default_factory=list)


class TaskJobPage(BaseModel):
    """异步任务分页响应。"""

    data: list[TaskJobRead]
    total: int
    page: int
    limit: int


class TaskDeadLetterRead(BaseModel):
    """异步任务死信响应。"""

    model_config = READ_SCHEMA_CONFIG

    id: int
    public_id: str
    job_id: int | None
    item_id: int | None
    job_public_id: str
    item_public_id: str
    task_type: str
    item_type: str
    queue_name: str
    stream_id: str
    stage: str
    worker_id: str
    attempt_count: int
    max_attempts: int
    error_code: str
    error_message: str
    payload: dict[str, Any]
    result: dict[str, Any]
    sort_order: int
    created_at: datetime
    updated_at: datetime
    disabled_at: datetime | None


class TaskStreamMessage(BaseModel):
    """Redis Stream 中的异步任务消息。"""

    event: str = Field(default="task.item.queued", description="消息事件类型")
    job_public_id: str = Field(min_length=1, max_length=36, description="任务公开标识")
    item_public_id: str = Field(min_length=1, max_length=36, description="任务子项公开标识")
    task_type: str = Field(min_length=1, max_length=100, description="任务类型标识")
    item_type: str = Field(default="", max_length=100, description="任务子项类型标识")
    queue_name: str = Field(default="default", max_length=120, description="任务队列名称")
    priority: int = Field(default=0, description="任务子项优先级")
    payload: dict[str, Any] = Field(default_factory=dict, description="任务子项参数")
    scheduled_at: datetime | None = Field(default=None, description="计划调度时间")
    created_at: datetime = Field(description="消息创建时间")


class TaskStreamRecord(BaseModel):
    """Redis Stream 消息读取结果。"""

    stream_id: str
    message: TaskStreamMessage
