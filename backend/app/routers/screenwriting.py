from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import get_session
from app.middlewares import common
from app.routers.base import BaseView, route
from app.schemas.screenwriting import (
    ScreenwritingChatPayload,
    ScreenwritingChatResponse,
    ScreenwritingRagWarmupResponse,
)
from app.services import project as project_service
from app.services import screenwriting as screenwriting_service

SessionDep = Annotated[AsyncSession, Depends(get_session)]

SCREENWRITING_ROUTE_MIDDLEWARES = [
    Depends(common.jwt_auth_middleware),
    Depends(common.request_duration_middleware),
]


class ScreenwritingView(BaseView):
    """剧本创作 Agent 接口。"""

    router_prefix = "/projects/{project_public_id}/novels/screenwriting"
    router_tags = ["screenwriting"]

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
        if isinstance(exc, screenwriting_service.ScreenwritingValidationError):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        if isinstance(exc, screenwriting_service.ScreenwritingServiceError):
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
        raise exc

    @route(
        "/chat",
        methods=["POST"],
        response_model=ScreenwritingChatResponse,
        middlewares=SCREENWRITING_ROUTE_MIDDLEWARES,
        summary="剧本创作 Agent 多轮对话",
        description="将用户输入发送给 Harness Agent，并返回聚合后的对话响应。",
    )
    async def chat_screenwriting(
        self,
        project_public_id: str,
        payload: ScreenwritingChatPayload,
        request: Request,
        session: SessionDep,
    ) -> ScreenwritingChatResponse:
        current_user_public_id = self._current_user_public_id(request)
        try:
            return await screenwriting_service.chat_screenwriting(
                session,
                project_public_id,
                current_user_public_id,
                payload,
            )
        except (project_service.ProjectServiceError, screenwriting_service.ScreenwritingServiceError) as exc:
            self._raise_as_http(exc)

    @route(
        "/chat/stream",
        methods=["POST"],
        middlewares=SCREENWRITING_ROUTE_MIDDLEWARES,
        summary="剧本创作 Agent 多轮对话流",
        description="将用户输入发送给 Harness Agent，并以 NDJSON 返回运行状态和增量内容。",
    )
    async def stream_chat_screenwriting(
        self,
        project_public_id: str,
        payload: ScreenwritingChatPayload,
        request: Request,
        session: SessionDep,
    ) -> StreamingResponse:
        current_user_public_id = self._current_user_public_id(request)
        try:
            events = await screenwriting_service.build_screenwriting_chat_stream(
                session,
                project_public_id,
                current_user_public_id,
                payload,
            )
        except (project_service.ProjectServiceError, screenwriting_service.ScreenwritingServiceError) as exc:
            self._raise_as_http(exc)

        async def render_events():
            async for event in events:
                if await request.is_disconnected():
                    break
                yield screenwriting_service.format_ndjson_event(event)

        return StreamingResponse(
            render_events(),
            media_type="application/x-ndjson",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "X-Content-Type-Options": "nosniff",
            },
        )

    @route(
        "/rag/warmup",
        methods=["POST"],
        response_model=ScreenwritingRagWarmupResponse,
        middlewares=SCREENWRITING_ROUTE_MIDDLEWARES,
        summary="预热剧本创作 RAG 向量索引",
        description="在用户进入剧本创作页面时异步调度当前项目的 RAG 向量索引构建。",
    )
    async def warmup_screenwriting_rag_index(
        self,
        project_public_id: str,
        request: Request,
        session: SessionDep,
    ) -> ScreenwritingRagWarmupResponse:
        current_user_public_id = self._current_user_public_id(request)
        try:
            return await screenwriting_service.warmup_screenwriting_rag_index(
                session,
                project_public_id,
                current_user_public_id,
            )
        except (project_service.ProjectServiceError, screenwriting_service.ScreenwritingServiceError) as exc:
            self._raise_as_http(exc)


router = ScreenwritingView()()
