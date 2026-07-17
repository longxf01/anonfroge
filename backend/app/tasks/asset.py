from __future__ import annotations

from typing import Any

from app.core.tasks.engine import AsyncTaskDefinition, TaskHandlerFailure
from app.services import asset as asset_service


async def extract_assets_task(context: Any) -> dict[str, Any]:
    """剧本资产抽取子任务处理器。"""

    payload = context.message.payload
    project_public_id = str(payload.get("project_public_id") or "").strip()
    current_user_public_id = str(payload.get("current_user_public_id") or "").strip()
    model_id = str(payload.get("model_id") or "").strip()
    episode_public_ids = _payload_str_list(payload.get("episode_public_ids"))
    if not project_public_id or not current_user_public_id or not model_id:
        raise ValueError("资产抽取任务参数不完整")

    try:
        result = await asset_service.extract_assets(
            context.session,
            project_public_id,
            current_user_public_id,
            model_id=model_id,
            episode_public_ids=episode_public_ids or None,
        )
        await context.session.commit()
    except asset_service.AssetServiceError as exc:
        await context.session.rollback()
        failure_result = {
            **exc.result,
            "episode_public_ids": episode_public_ids,
        }
        raise TaskHandlerFailure(
            str(exc),
            error_code="asset_extract_failed",
            result=failure_result,
        ) from exc

    assets = result["assets"]
    return {
        "created": int(result["created"]),
        "updated": int(result["updated"]),
        "asset_public_ids": [asset.public_id for asset in assets],
        "episode_public_ids": episode_public_ids,
        "model_id": result.get("model_id") or model_id,
        "messages": result.get("messages") or [],
        "composed_prompt": str(result.get("composed_prompt") or ""),
        "raw_output": str(result.get("raw_output") or ""),
        "output_text": str(result.get("output_text") or ""),
    }


def _payload_str_list(value: Any) -> list[str]:
    """把任务 payload 中的列表值清理为字符串列表。"""

    if not isinstance(value, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


async def autocomplete_asset_task(context: Any) -> dict[str, Any]:
    """资产描述补全子任务处理器。"""

    payload = context.message.payload
    project_public_id = str(payload.get("project_public_id") or "").strip()
    current_user_public_id = str(payload.get("current_user_public_id") or "").strip()
    model_id = str(payload.get("model_id") or "").strip()
    asset_public_id = str(payload.get("asset_public_id") or "").strip()
    if not project_public_id or not current_user_public_id or not model_id or not asset_public_id:
        raise ValueError("资产补全任务参数不完整")

    try:
        result = await asset_service.autocomplete_asset(
            context.session,
            project_public_id,
            current_user_public_id,
            asset_public_id=asset_public_id,
            model_id=model_id,
        )
        await context.session.commit()
    except asset_service.AssetServiceError as exc:
        await context.session.rollback()
        raise TaskHandlerFailure(
            str(exc),
            error_code="asset_autocomplete_failed",
            result={**exc.result, "asset_public_id": asset_public_id},
        ) from exc

    return {
        "asset_public_id": result["asset"].public_id,
        "model_id": result.get("model_id") or model_id,
        "messages": result.get("messages") or [],
        "composed_prompt": str(result.get("composed_prompt") or ""),
        "raw_output": str(result.get("raw_output") or ""),
        "output_text": str(result.get("output_text") or ""),
    }


ASYNC_TASKS = (
    AsyncTaskDefinition(asset_service.ASSET_EXTRACT_TASK_TYPE, extract_assets_task),
    AsyncTaskDefinition(asset_service.ASSET_AUTOCOMPLETE_TASK_TYPE, autocomplete_asset_task),
)