from __future__ import annotations

from typing import Any

from app.core.tasks.engine import AsyncTaskDefinition, TaskHandlerFailure
from app.services import storyboard as storyboard_service


async def generate_storyboard_task(context: Any) -> dict[str, Any]:
    """Storyboard generation task item handler."""

    payload = context.message.payload
    project_public_id = str(payload.get("project_public_id") or "").strip()
    current_user_public_id = str(payload.get("current_user_public_id") or "").strip()
    model_id = str(payload.get("model_id") or "").strip()
    episode_public_id = str(payload.get("episode_public_id") or "").strip()
    art_style = str(payload.get("art_style") or "").strip()
    director_style = str(payload.get("director_style") or "").strip()
    if not project_public_id or not current_user_public_id or not model_id or not episode_public_id:
        raise ValueError("分镜生成任务参数不完整")

    try:
        result = await storyboard_service.generate_storyboard(
            context.session,
            project_public_id,
            current_user_public_id,
            episode_public_id,
            model_id=model_id,
            art_style=art_style,
            director_style=director_style,
        )
        await context.session.commit()
    except storyboard_service.StoryboardServiceError as exc:
        await context.session.rollback()
        raise TaskHandlerFailure(
            str(exc),
            error_code="storyboard_generation_failed",
            result={**exc.result, "episode_public_id": episode_public_id},
        ) from exc

    shots = result["shots"]
    return {
        "created": int(result["created"]),
        "updated": int(result["updated"]),
        "shot_public_ids": [shot.public_id for shot in shots],
        "episode_public_id": episode_public_id,
        "episode_index": result.get("episode_index"),
        "model_id": result.get("model_id") or model_id,
        "art_style": result.get("art_style") or art_style,
        "director_style": result.get("director_style") or director_style,
        "parse_status": result.get("parse_status") or "",
        "storyboard_timing": result.get("storyboard_timing") or {},
        "messages": result.get("messages") or [],
        "composed_prompt": str(result.get("composed_prompt") or ""),
        "raw_output": str(result.get("raw_output") or ""),
        "output_text": str(result.get("output_text") or ""),
    }


ASYNC_TASKS = (
    AsyncTaskDefinition(storyboard_service.STORYBOARD_GENERATE_TASK_TYPE, generate_storyboard_task),
)