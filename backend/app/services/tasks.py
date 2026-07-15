from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from typing import Any

from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.tasks import TaskItem, TaskJob, TaskStatus, utc_now
from app.schemas.tasks import (
    TaskItemCreate,
    TaskItemRead,
    TaskJobCreate,
    TaskJobDetail,
    TaskJobPage,
    TaskJobRead,
    TaskStatusUpdate,
)


TERMINAL_STATUSES = {
    TaskStatus.SUCCEEDED,
    TaskStatus.FAILED,
    TaskStatus.CANCELLED,
    TaskStatus.PARTIAL,
}
RUNNABLE_ITEM_STATUSES = {
    TaskStatus.PENDING,
    TaskStatus.QUEUED,
}
CANCELLABLE_ITEM_STATUSES = {
    TaskStatus.PENDING,
    TaskStatus.QUEUED,
    TaskStatus.PAUSED,
}
RETRYABLE_ITEM_STATUSES = {
    TaskStatus.FAILED,
    TaskStatus.CANCELLED,
}


class TaskServiceError(Exception):
    """异步任务服务层基础异常。"""


class TaskJobNotFoundError(TaskServiceError):
    """异步任务不存在。"""


class TaskItemNotFoundError(TaskServiceError):
    """异步任务子项不存在。"""


class TaskValidationError(TaskServiceError):
    """异步任务请求不合法。"""


async def create_task_job(session: AsyncSession, payload: TaskJobCreate) -> TaskJobDetail:
    """创建异步任务及初始子项。"""
    now = utc_now()
    job = TaskJob(
        task_type=payload.task_type.strip(),
        queue_name=payload.queue_name.strip() or "default",
        name=payload.name.strip(),
        status=TaskStatus.PENDING,
        created_by=payload.created_by.strip(),
        idempotency_key=payload.idempotency_key.strip(),
        priority=payload.priority,
        total_items=len(payload.items),
        payload=_dump_json(payload.payload),
        scheduled_at=payload.scheduled_at,
        created_at=now,
        updated_at=now,
    )
    session.add(job)
    await session.flush()
    if job.id is None:
        raise TaskValidationError("任务创建失败")

    items = [_build_task_item(job, item_payload, now) for item_payload in payload.items]
    if items:
        session.add_all(items)

    await _commit_and_refresh_task_models(session, job, items)
    return _to_job_detail(job, items)


async def append_task_items(
    session: AsyncSession,
    job_public_id: str,
    payloads: list[TaskItemCreate],
) -> TaskJobDetail:
    """追加异步任务子项。"""
    job = await _get_task_job_model_or_raise(session, job_public_id)
    now = utc_now()
    items = [_build_task_item(job, item_payload, now) for item_payload in payloads]
    if items:
        session.add_all(items)
        job.total_items += len(items)
        job.updated_at = now
        session.add(job)
    await _commit_and_refresh_task_models(session, job, items)
    return _to_job_detail(job, await _list_task_item_models(session, job.id or 0))


async def list_task_jobs(
    session: AsyncSession,
    *,
    page: int = 1,
    limit: int = 20,
    task_type: str = "",
    status: TaskStatus | None = None,
    created_by: str = "",
    queue_name: str = "",
) -> TaskJobPage:
    """分页查询异步任务列表。"""
    page = max(page, 1)
    limit = min(max(limit, 1), 100)
    conditions = [TaskJob.disabled_at.is_(None)]
    if status is not None:
        conditions.append(TaskJob.status == status)
    for value, column in (
        (task_type, TaskJob.task_type),
        (created_by, TaskJob.created_by),
        (queue_name, TaskJob.queue_name),
    ):
        if value:
            conditions.append(column == value.strip())

    count_statement = select(func.count()).select_from(TaskJob).where(*conditions)
    count_result = await session.exec(count_statement)
    total = int(count_result.one())

    statement = (
        select(TaskJob)
        .where(*conditions)
        .order_by(TaskJob.created_at.desc(), TaskJob.id.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    result = await session.exec(statement)
    return TaskJobPage(
        data=[_to_job_read(job) for job in result.all()],
        total=total,
        page=page,
        limit=limit,
    )


async def get_task_job(
    session: AsyncSession,
    job_public_id: str,
    *,
    include_items: bool = False,
) -> TaskJobRead | TaskJobDetail:
    """按公开标识获取异步任务。"""
    job = await _get_task_job_model_or_raise(session, job_public_id)
    if not include_items:
        return _to_job_read(job)
    return _to_job_detail(job, await _list_task_item_models(session, job.id or 0))


async def list_task_items(
    session: AsyncSession,
    job_public_id: str,
    *,
    status: TaskStatus | None = None,
) -> list[TaskItemRead]:
    """查询异步任务子项列表。"""
    job = await _get_task_job_model_or_raise(session, job_public_id)
    return [_to_item_read(item) for item in await _list_task_item_models(session, job.id or 0, status=status)]


async def get_task_item(session: AsyncSession, item_public_id: str) -> TaskItemRead:
    """按公开标识获取异步任务子项。"""
    return _to_item_read(await _get_task_item_model_or_raise(session, item_public_id))


async def update_task_job_status(
    session: AsyncSession,
    job_public_id: str,
    payload: TaskStatusUpdate,
) -> TaskJobRead:
    """更新异步任务状态。"""
    job = await _get_task_job_model_or_raise(session, job_public_id)
    _apply_status_update(job, payload)
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return _to_job_read(job)


async def update_task_item_status(
    session: AsyncSession,
    item_public_id: str,
    payload: TaskStatusUpdate,
    *,
    refresh_job: bool = True,
) -> TaskItemRead:
    """更新异步任务子项状态，并按需刷新父任务进度。"""
    item = await _get_task_item_model_or_raise(session, item_public_id)
    _apply_status_update(item, payload)
    if payload.worker_id is not None:
        item.worker_id = payload.worker_id.strip()
    session.add(item)
    if refresh_job:
        job = await _get_task_job_model_by_id_or_raise(session, item.job_id)
        await refresh_task_job_progress(session, job)
    await session.commit()
    await session.refresh(item)
    return _to_item_read(item)


async def mark_task_item_running(
    session: AsyncSession,
    item_public_id: str,
    worker_id: str,
) -> bool:
    """将可执行任务子项标记为运行中；状态不允许时返回 False。"""
    item = await _get_task_item_model_or_raise(session, item_public_id)
    if item.status not in RUNNABLE_ITEM_STATUSES:
        return False

    _apply_status_update(
        item,
        TaskStatusUpdate(
            status=TaskStatus.RUNNING,
            worker_id=worker_id,
        ),
    )
    item.worker_id = worker_id.strip()
    session.add(item)
    job = await _get_task_job_model_by_id_or_raise(session, item.job_id)
    await refresh_task_job_progress(session, job)
    await session.commit()
    await session.refresh(item)
    return True


async def delete_task_job(session: AsyncSession, job_public_id: str) -> None:
    """软删除异步任务及其未删除的子项。"""
    job = await _get_task_job_model_or_raise(session, job_public_id)
    if job.id is None:
        raise TaskJobNotFoundError("异步任务不存在")

    now = utc_now()
    job.disabled_at = now
    job.updated_at = now
    session.add(job)

    items = await _list_task_item_models(session, job.id)
    for item in items:
        item.disabled_at = now
        item.updated_at = now
        session.add(item)

    await session.commit()


async def cancel_task_item(session: AsyncSession, item_public_id: str) -> TaskItemRead:
    """取消异步任务子项，并刷新父任务进度。"""
    item = await _get_task_item_model_or_raise(session, item_public_id)
    if item.status not in CANCELLABLE_ITEM_STATUSES:
        raise TaskValidationError("只有待处理、已入队或已暂停的任务子项可以取消")
    job = await _get_task_job_model_by_id_or_raise(session, item.job_id)

    now = utc_now()
    item.status = TaskStatus.CANCELLED
    item.error_code = "task_item_cancelled"
    item.error_message = "任务子项已取消"
    item.completed_at = now
    item.updated_at = now
    session.add(item)
    await refresh_task_job_progress(session, job)
    await session.commit()
    await session.refresh(item)
    return _to_item_read(item)


async def retry_task_item(session: AsyncSession, item_public_id: str) -> TaskItemRead:
    """将失败或已取消的异步任务子项重置为待处理。"""
    item = await _get_task_item_model_or_raise(session, item_public_id)
    if item.status not in RETRYABLE_ITEM_STATUSES:
        raise TaskValidationError("只有失败或已取消的任务子项可以重试")
    job = await _get_task_job_model_by_id_or_raise(session, item.job_id)

    now = utc_now()
    item.status = TaskStatus.PENDING
    item.worker_id = ""
    item.result = "{}"
    item.error_code = ""
    item.error_message = ""
    item.started_at = None
    item.heartbeat_at = None
    item.completed_at = None
    item.scheduled_at = None
    item.updated_at = now
    session.add(item)
    await refresh_task_job_progress(session, job)
    await session.commit()
    await session.refresh(item)
    return _to_item_read(item)


async def delete_task_item(session: AsyncSession, item_public_id: str) -> None:
    """软删除异步任务子项，并刷新父任务进度。"""
    item = await _get_task_item_model_or_raise(session, item_public_id)
    job = await _get_task_job_model_by_id_or_raise(session, item.job_id)

    now = utc_now()
    item.disabled_at = now
    item.updated_at = now
    session.add(item)
    await refresh_task_job_progress(session, job)
    await session.commit()


async def refresh_task_job_progress(session: AsyncSession, job: TaskJob) -> TaskJob:
    """重新统计任务子项进度，并推导父任务状态。"""
    if job.id is None:
        raise TaskValidationError("任务内部主键不能为空")

    statement = (
        select(TaskItem.status, func.count())
        .where(TaskItem.job_id == job.id, TaskItem.disabled_at.is_(None))
        .group_by(TaskItem.status)
    )
    result = await session.exec(statement)
    counts = Counter({status: int(count) for status, count in result.all()})
    total = sum(counts.values())
    succeeded = counts[TaskStatus.SUCCEEDED]
    failed = counts[TaskStatus.FAILED]
    cancelled = counts[TaskStatus.CANCELLED]
    running = counts[TaskStatus.RUNNING]
    queued = counts[TaskStatus.QUEUED]
    pending = counts[TaskStatus.PENDING]

    now = utc_now()
    job.total_items = total
    job.completed_items = succeeded
    job.failed_items = failed
    job.cancelled_items = cancelled

    terminal_count = succeeded + failed + cancelled
    if total == 0:
        job.status = TaskStatus.PENDING
        job.completed_at = None
    elif terminal_count == total:
        if failed and succeeded:
            job.status = TaskStatus.PARTIAL
        elif failed:
            job.status = TaskStatus.FAILED
        elif cancelled and not succeeded:
            job.status = TaskStatus.CANCELLED
        else:
            job.status = TaskStatus.SUCCEEDED
        job.completed_at = job.completed_at or now
    elif running:
        job.status = TaskStatus.RUNNING
        job.started_at = job.started_at or now
        job.completed_at = None
    elif queued:
        job.status = TaskStatus.QUEUED
        job.completed_at = None
    elif pending:
        job.status = TaskStatus.PENDING
        job.completed_at = None

    job.updated_at = now
    session.add(job)
    return job


async def _get_task_job_model_or_raise(session: AsyncSession, job_public_id: str) -> TaskJob:
    statement = select(TaskJob).where(TaskJob.public_id == job_public_id, TaskJob.disabled_at.is_(None))
    return await _first_or_raise(session, statement, TaskJobNotFoundError("异步任务不存在"))


async def _get_task_job_model_by_id_or_raise(session: AsyncSession, job_id: int) -> TaskJob:
    statement = select(TaskJob).where(TaskJob.id == job_id, TaskJob.disabled_at.is_(None))
    return await _first_or_raise(session, statement, TaskJobNotFoundError("异步任务不存在"))


async def _get_task_item_model_or_raise(session: AsyncSession, item_public_id: str) -> TaskItem:
    statement = select(TaskItem).where(TaskItem.public_id == item_public_id, TaskItem.disabled_at.is_(None))
    return await _first_or_raise(session, statement, TaskItemNotFoundError("异步任务子项不存在"))


async def _list_task_item_models(
    session: AsyncSession,
    job_id: int,
    *,
    status: TaskStatus | None = None,
) -> list[TaskItem]:
    conditions = [TaskItem.job_id == job_id, TaskItem.disabled_at.is_(None)]
    if status is not None:
        conditions.append(TaskItem.status == status)
    statement = select(TaskItem).where(*conditions).order_by(TaskItem.priority.desc(), TaskItem.id)
    result = await session.exec(statement)
    return list(result.all())


def _build_task_item(job: TaskJob, payload: TaskItemCreate, now: datetime) -> TaskItem:
    item_type = payload.item_type.strip() or job.task_type
    return TaskItem(
        job_id=int(job.id or 0),
        item_type=item_type,
        item_key=payload.item_key.strip() if payload.item_key else None,
        status=TaskStatus.PENDING,
        priority=payload.priority,
        max_attempts=payload.max_attempts,
        payload=_dump_json(payload.payload),
        scheduled_at=payload.scheduled_at or job.scheduled_at,
        created_at=now,
        updated_at=now,
    )


async def _commit_and_refresh_task_models(
    session: AsyncSession,
    job: TaskJob,
    items: list[TaskItem],
) -> None:
    await session.commit()
    await session.refresh(job)
    for item in items:
        await session.refresh(item)


async def _first_or_raise(session: AsyncSession, statement: Any, exc: Exception) -> Any:
    result = await session.exec(statement)
    value = result.first()
    if value is None:
        raise exc
    return value


def _apply_status_update(target: TaskJob | TaskItem, payload: TaskStatusUpdate) -> None:
    now = utc_now()
    target.status = payload.status
    if payload.result is not None:
        target.result = _dump_json(payload.result)
    target.error_code = payload.error_code.strip()
    target.error_message = payload.error_message.strip()
    if payload.status == TaskStatus.RUNNING:
        target.started_at = target.started_at or now
        if isinstance(target, TaskItem):
            target.attempt_count += 1
            target.heartbeat_at = now
        target.completed_at = None
    if payload.status in TERMINAL_STATUSES:
        target.completed_at = target.completed_at or now
    target.updated_at = now


def _dump_json(value: dict[str, Any] | None) -> str:
    try:
        return json.dumps(value or {}, ensure_ascii=False, separators=(",", ":"))
    except TypeError as exc:
        raise TaskValidationError("任务参数必须是可序列化的 JSON 对象") from exc


def _load_json(value: str) -> dict[str, Any]:
    if not value:
        return {}
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return {"_raw": value}
    if isinstance(loaded, dict):
        return loaded
    return {"value": loaded}


def _to_job_read(job: TaskJob) -> TaskJobRead:
    return TaskJobRead(**_read_schema_values(job, "payload", "result"))


def _to_job_detail(job: TaskJob, items: list[TaskItem]) -> TaskJobDetail:
    return TaskJobDetail(**_to_job_read(job).model_dump(), items=[_to_item_read(item) for item in items])


def _to_item_read(item: TaskItem) -> TaskItemRead:
    return TaskItemRead(**_read_schema_values(item, "payload", "result"))


def _read_schema_values(model: Any, *json_fields: str) -> dict[str, Any]:
    values = model.model_dump()
    values["id"] = int(model.id or 0)
    for field in json_fields:
        values[field] = _load_json(getattr(model, field))
    return values
