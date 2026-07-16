from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import get_session
from app.middlewares import common
from app.routers.base import BaseView, route
from app.schemas.script import (
    ScriptEpisodeRead,
    ScriptPlanDetail,
    ScriptPlanSummary,
    ScriptSyncPayload,
)
from app.services import project as project_service
from app.services import script as script_service

SessionDep = Annotated[AsyncSession, Depends(get_session)]

SCRIPT_ROUTE_MIDDLEWARES = [
    Depends(common.jwt_auth_middleware),
    Depends(common.request_duration_middleware),
]


class ScriptView(BaseView):
    """剧本管理接口：剧本创作工作台产物的查询与同步。"""

    router_prefix = "/projects/{project_public_id}/scripts"
    router_tags = ["script"]

    @staticmethod
    def _current_user_public_id(request: Request) -> str:
        public_id = getattr(request.state, "current_user_public_id", None)
        if not public_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="请提供 access token",
                headers=common.BEARER_AUTH_HEADER,
            )
        return str(public_id)

    @staticmethod
    def _raise_as_http(exc: Exception) -> None:
        if isinstance(exc, project_service.ProjectNotFoundError):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        if isinstance(exc, project_service.ProjectAccessDeniedError):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
        if isinstance(exc, script_service.ScriptServiceError):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        raise exc

    @route(
        "/plans",
        methods=["GET"],
        response_model=list[ScriptPlanSummary],
        middlewares=SCRIPT_ROUTE_MIDDLEWARES,
        summary="列出剧本计划",
        description="返回当前项目与用户的剧本计划列表（按更新时间倒序）。",
    )
    async def list_script_plans(
        self,
        project_public_id: str,
        request: Request,
        session: SessionDep,
    ) -> list[ScriptPlanSummary]:
        current_user_public_id = self._current_user_public_id(request)
        try:
            plans = await script_service.list_plans(session, project_public_id, current_user_public_id)
        except (project_service.ProjectServiceError, script_service.ScriptServiceError) as exc:
            self._raise_as_http(exc)
        return [ScriptPlanSummary.model_validate(plan) for plan in plans]

    @route(
        "/plans/{plan_public_id}",
        methods=["GET"],
        response_model=ScriptPlanDetail,
        middlewares=SCRIPT_ROUTE_MIDDLEWARES,
        summary="剧本计划详情",
        description="返回指定剧本计划及其分集与场次结构。",
    )
    async def get_script_plan(
        self,
        project_public_id: str,
        plan_public_id: str,
        request: Request,
        session: SessionDep,
    ) -> ScriptPlanDetail:
        current_user_public_id = self._current_user_public_id(request)
        try:
            plan, episodes = await script_service.get_plan_detail(
                session,
                project_public_id,
                current_user_public_id,
                plan_public_id,
            )
        except (project_service.ProjectServiceError, script_service.ScriptServiceError) as exc:
            self._raise_as_http(exc)
        detail = ScriptPlanDetail.model_validate(plan)
        detail.episodes = [ScriptEpisodeRead.from_model(episode) for episode in episodes]
        return detail

    @route(
        "/sync",
        methods=["POST"],
        response_model=ScriptPlanDetail,
        middlewares=SCRIPT_ROUTE_MIDDLEWARES,
        summary="同步剧本创作工作台到剧本管理",
        description="把当前剧本创作会话的剧本草案解析为分集并落库（幂等，已锁定集不覆盖）。",
    )
    async def sync_script_plan(
        self,
        project_public_id: str,
        payload: ScriptSyncPayload,
        request: Request,
        session: SessionDep,
    ) -> ScriptPlanDetail:
        current_user_public_id = self._current_user_public_id(request)
        try:
            plan = await script_service.sync_current_workspace(
                session,
                project_public_id,
                current_user_public_id,
                title=payload.title,
            )
            await session.commit()
            plan, episodes = await script_service.get_plan_detail(
                session,
                project_public_id,
                current_user_public_id,
                plan.public_id,
            )
        except (project_service.ProjectServiceError, script_service.ScriptServiceError) as exc:
            await session.rollback()
            self._raise_as_http(exc)
        detail = ScriptPlanDetail.model_validate(plan)
        detail.episodes = [ScriptEpisodeRead.from_model(episode) for episode in episodes]
        return detail


router = ScriptView().router