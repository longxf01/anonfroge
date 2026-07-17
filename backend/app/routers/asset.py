from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Query, Request, Response, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import get_session
from app.middlewares import common
from app.routers.base import BaseView, route
from app.schemas.asset import (
    AssetAssociationRequest,
    AssetAssociationResult,
    AssetDetailRead,
    AssetEpisodeBrief,
    AssetExtractRequest,
    AssetRead,
)
from app.schemas.tasks import TaskJobDetail
from app.services import asset as asset_service
from app.services import project as project_service
from app.services import tasks as task_service


SessionDep = Annotated[AsyncSession, Depends(get_session)]

ASSET_ROUTE_MIDDLEWARES = [
    Depends(common.jwt_auth_middleware),
    Depends(common.request_duration_middleware),
]


class AssetView(BaseView):
    """资产抽取接口。"""

    router_prefix = "/projects/{project_public_id}/assets"
    router_tags = ["asset"]

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
        if isinstance(exc, asset_service.AssetNotFoundError):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        if isinstance(exc, asset_service.AssetServiceError):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        if isinstance(exc, task_service.TaskServiceError):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        raise exc

    @route(
        "/extract",
        methods=["POST"],
        response_model=TaskJobDetail,
        status_code=status.HTTP_202_ACCEPTED,
        middlewares=ASSET_ROUTE_MIDDLEWARES,
        summary="从剧本抽取资产",
    )
    async def extract_assets(
        self,
        project_public_id: str,
        payload: AssetExtractRequest,
        request: Request,
        session: SessionDep,
    ) -> TaskJobDetail:
        current_user_public_id = self._current_user_public_id(request)
        try:
            return await asset_service.submit_extract_assets_task(
                session,
                project_public_id,
                current_user_public_id,
                model_id=payload.model_id,
                episode_public_ids=payload.episode_public_ids or None,
            )
        except (project_service.ProjectServiceError, asset_service.AssetServiceError, task_service.TaskServiceError) as exc:
            await session.rollback()
            self._raise_as_http(exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="资产抽取任务提交失败")

    @route(
        "",
        methods=["GET"],
        response_model=list[AssetRead],
        middlewares=ASSET_ROUTE_MIDDLEWARES,
        summary="列出资产",
    )
    async def list_assets(
        self,
        project_public_id: str,
        request: Request,
        session: SessionDep,
        asset_type: str = Query(default="", alias="assetType"),
    ) -> list[AssetRead]:
        current_user_public_id = self._current_user_public_id(request)
        try:
            assets = await asset_service.list_assets(
                session,
                project_public_id,
                current_user_public_id,
                asset_type=asset_type,
            )
        except (project_service.ProjectServiceError, asset_service.AssetServiceError) as exc:
            self._raise_as_http(exc)
        return [AssetRead.model_validate(asset) for asset in assets]

    @route(
        "/{asset_public_id}",
        methods=["GET"],
        response_model=AssetDetailRead,
        middlewares=ASSET_ROUTE_MIDDLEWARES,
        summary="读取资产详情",
    )
    async def get_asset(
        self,
        project_public_id: str,
        asset_public_id: str,
        request: Request,
        session: SessionDep,
    ) -> AssetDetailRead:
        current_user_public_id = self._current_user_public_id(request)
        try:
            asset = await asset_service.get_asset(
                session,
                project_public_id,
                current_user_public_id,
                asset_public_id,
            )
            episode_items = await asset_service.get_asset_episode_items(
                session,
                project_public_id,
                current_user_public_id,
                asset,
            )
        except (project_service.ProjectServiceError, asset_service.AssetServiceError) as exc:
            self._raise_as_http(exc)
        detail = AssetDetailRead.model_validate(asset)
        detail.episode_items = [AssetEpisodeBrief.model_validate(item) for item in episode_items]
        return detail

    @route(
        "/associations",
        methods=["POST"],
        response_model=AssetAssociationResult,
        middlewares=ASSET_ROUTE_MIDDLEWARES,
        summary="设置分集关联资产",
    )
    async def set_episode_assets(
        self,
        project_public_id: str,
        payload: AssetAssociationRequest,
        request: Request,
        session: SessionDep,
    ) -> AssetAssociationResult:
        current_user_public_id = self._current_user_public_id(request)
        try:
            result = await asset_service.set_episode_assets(
                session,
                project_public_id,
                current_user_public_id,
                payload.episode_public_id,
                payload.asset_public_ids,
            )
            await session.commit()
        except (project_service.ProjectServiceError, asset_service.AssetServiceError) as exc:
            await session.rollback()
            self._raise_as_http(exc)
        return AssetAssociationResult(
            affected=result["affected"],
            assets=[AssetRead.model_validate(asset) for asset in result["assets"]],
        )

    @route(
        "/{asset_public_id}/lock",
        methods=["POST"],
        response_model=AssetRead,
        middlewares=ASSET_ROUTE_MIDDLEWARES,
        summary="锁定资产",
    )
    async def lock_asset(
        self,
        project_public_id: str,
        asset_public_id: str,
        request: Request,
        session: SessionDep,
    ) -> AssetRead:
        return await self._set_asset_lock(project_public_id, asset_public_id, request, session, locked=True)

    @route(
        "/{asset_public_id}/unlock",
        methods=["POST"],
        response_model=AssetRead,
        middlewares=ASSET_ROUTE_MIDDLEWARES,
        summary="解锁资产",
    )
    async def unlock_asset(
        self,
        project_public_id: str,
        asset_public_id: str,
        request: Request,
        session: SessionDep,
    ) -> AssetRead:
        return await self._set_asset_lock(project_public_id, asset_public_id, request, session, locked=False)

    async def _set_asset_lock(
        self,
        project_public_id: str,
        asset_public_id: str,
        request: Request,
        session: AsyncSession,
        *,
        locked: bool,
    ) -> AssetRead:
        current_user_public_id = self._current_user_public_id(request)
        try:
            asset = await asset_service.set_asset_lock(
                session,
                project_public_id,
                current_user_public_id,
                asset_public_id,
                locked=locked,
            )
            await session.commit()
        except (project_service.ProjectServiceError, asset_service.AssetServiceError) as exc:
            await session.rollback()
            self._raise_as_http(exc)
        return AssetRead.model_validate(asset)

    @route(
        "/{asset_public_id}",
        methods=["DELETE"],
        status_code=status.HTTP_204_NO_CONTENT,
        middlewares=ASSET_ROUTE_MIDDLEWARES,
        summary="删除资产",
    )
    async def delete_asset(
        self,
        project_public_id: str,
        asset_public_id: str,
        request: Request,
        session: SessionDep,
    ) -> Response:
        current_user_public_id = self._current_user_public_id(request)
        try:
            asset = await asset_service.get_asset(
                session,
                project_public_id,
                current_user_public_id,
                asset_public_id,
            )
            await session.delete(asset)
            await session.commit()
        except (project_service.ProjectServiceError, asset_service.AssetServiceError) as exc:
            await session.rollback()
            self._raise_as_http(exc)
        return Response(status_code=status.HTTP_204_NO_CONTENT)


router = AssetView().router
