from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Query, Response, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import get_session
from app.core.tasks.engine import default_async_task_engine
from app.models.tasks import TaskStatus
from app.routers.base import BaseView, route
from app.schemas.tasks import TaskItemRead, TaskJobCreate, TaskJobDetail, TaskJobPage, TaskJobRead

SessionDep = Annotated[AsyncSession, Depends(get_session)]


class TaskView(BaseView):
    """异步任务类视图。"""

    router_prefix = "/tasks"
    router_tags = ["tasks"]

    @route(
        "",
        methods=["POST"],
        response_model=TaskJobDetail,
        status_code=status.HTTP_201_CREATED,
        summary="添加单个异步任务",
        description="创建单个异步任务记录，不立即投递到执行队列。",
    )
    async def create_task(
        self,
        payload: TaskJobCreate,
        session: SessionDep,
    ) -> TaskJobDetail:
        """添加单个异步任务。"""
        return await default_async_task_engine.create_task_job(session, payload)

    @route(
        "/enqueue",
        methods=["POST"],
        response_model=TaskJobDetail,
        status_code=status.HTTP_202_ACCEPTED,
        summary="添加并启动单个异步任务",
        description="创建单个异步任务记录，并立即投递可执行的任务子项。",
    )
    async def create_and_enqueue_task(
        self,
        payload: TaskJobCreate,
        session: SessionDep,
    ) -> TaskJobDetail:
        """添加并启动单个异步任务。"""
        return await default_async_task_engine.create_and_enqueue_task_job(session, payload)

    @route(
        "/batch",
        methods=["POST"],
        response_model=list[TaskJobDetail],
        status_code=status.HTTP_201_CREATED,
        summary="批量添加异步任务",
        description="批量创建异步任务记录，不立即投递到执行队列。",
    )
    async def create_tasks(
        self,
        payloads: list[TaskJobCreate],
        session: SessionDep,
    ) -> list[TaskJobDetail]:
        """批量添加异步任务。"""
        jobs: list[TaskJobDetail] = []
        for payload in payloads:
            jobs.append(await default_async_task_engine.create_task_job(session, payload))
        return jobs

    @route(
        "/batch/enqueue",
        methods=["POST"],
        response_model=list[TaskJobDetail],
        status_code=status.HTTP_202_ACCEPTED,
        summary="批量添加并启动异步任务",
        description="批量创建异步任务记录，并立即投递可执行的任务子项。",
    )
    async def create_and_enqueue_tasks(
        self,
        payloads: list[TaskJobCreate],
        session: SessionDep,
    ) -> list[TaskJobDetail]:
        """批量添加并启动异步任务。"""
        jobs: list[TaskJobDetail] = []
        for payload in payloads:
            jobs.append(await default_async_task_engine.create_and_enqueue_task_job(session, payload))
        return jobs

    @route(
        "/{job_public_id}/start",
        methods=["POST"],
        response_model=list[str],
        status_code=status.HTTP_202_ACCEPTED,
        summary="开启任务",
        description="将指定异步任务的可执行子项投递到任务队列。",
    )
    async def start_task(
        self,
        job_public_id: str,
        session: SessionDep,
    ) -> list[str]:
        """开启指定异步任务。"""
        records = await default_async_task_engine.enqueue_task_job(session, job_public_id)
        return [record.stream_id for record in records]

    @route(
        "/{job_public_id}/pause",
        methods=["POST"],
        response_model=TaskJobRead,
        summary="暂停任务",
        description="暂停指定异步任务，避免继续调度未执行的任务子项。",
    )
    async def pause_task(
        self,
        job_public_id: str,
        session: SessionDep,
    ) -> TaskJobRead:
        """暂停指定异步任务。"""
        return await default_async_task_engine.pause_task_job(session, job_public_id)

    @route(
        "/{job_public_id}/resume",
        methods=["POST"],
        response_model=list[str],
        status_code=status.HTTP_202_ACCEPTED,
        summary="恢复任务",
        description="恢复指定异步任务，并重新投递可执行的任务子项。",
    )
    async def resume_task(
        self,
        job_public_id: str,
        session: SessionDep,
    ) -> list[str]:
        """恢复指定异步任务。"""
        records = await default_async_task_engine.resume_task_job(session, job_public_id)
        return [record.stream_id for record in records]

    @route(
        "/{job_public_id}/cancel",
        methods=["POST"],
        response_model=TaskJobRead,
        summary="取消任务",
        description="取消指定异步任务及其尚未完成的任务子项。",
    )
    async def cancel_task(
        self,
        job_public_id: str,
        session: SessionDep,
    ) -> TaskJobRead:
        """取消指定异步任务。"""
        return await default_async_task_engine.cancel_task_job(session, job_public_id)

    @route(
        "/items/{item_public_id}/cancel",
        methods=["POST"],
        response_model=TaskItemRead,
        summary="取消任务子项",
        description="取消指定异步任务子项，并刷新所属任务的进度统计。",
    )
    async def cancel_task_item(
        self,
        item_public_id: str,
        session: SessionDep,
    ) -> TaskItemRead:
        """取消指定异步任务子项。"""
        return await default_async_task_engine.cancel_task_item(session, item_public_id)

    @route(
        "/items/{item_public_id}/retry",
        methods=["POST"],
        response_model=TaskItemRead,
        status_code=status.HTTP_202_ACCEPTED,
        summary="重试任务子项",
        description="将指定异步任务子项重置为待执行状态，等待后续重新调度。",
    )
    async def retry_task_item(
        self,
        item_public_id: str,
        session: SessionDep,
    ) -> TaskItemRead:
        """重试指定异步任务子项。"""
        return await default_async_task_engine.retry_task_item(session, item_public_id)

    @route(
        "/{job_public_id}",
        methods=["DELETE"],
        response_model=None,
        status_code=status.HTTP_204_NO_CONTENT,
        summary="删除任务",
        description="软删除指定异步任务及其任务子项。",
    )
    async def delete_task(
        self,
        job_public_id: str,
        session: SessionDep,
    ) -> Response:
        """删除指定异步任务。"""
        await default_async_task_engine.delete_task_job(session, job_public_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @route(
        "/{job_public_id}",
        methods=["GET"],
        response_model=TaskJobDetail,
        summary="查看单个任务",
        description="查看指定异步任务详情，并包含任务子项列表。",
    )
    async def get_task(
        self,
        job_public_id: str,
        session: SessionDep,
    ) -> TaskJobDetail:
        """查看单个异步任务。"""
        return await default_async_task_engine.get_task_job(
            session,
            job_public_id,
            include_items=True,
        )

    @route(
        "",
        methods=["GET"],
        response_model=TaskJobPage,
        summary="查看批量任务",
        description="按分页和筛选条件查看异步任务列表。",
    )
    async def list_tasks(
        self,
        session: SessionDep,
        page: int = Query(default=1, ge=1),
        limit: int = Query(default=20, ge=1, le=100),
        task_type: str = "",
        queue_name: str = "",
        status_: TaskStatus | None = Query(default=None, alias="status"),
    ) -> TaskJobPage:
        """查看批量异步任务。"""
        return await default_async_task_engine.list_task_jobs(
            session,
            page=page,
            limit=limit,
            task_type=task_type,
            queue_name=queue_name,
            status=status_,
        )


router = TaskView()()
