from __future__ import annotations

from typing import Any

from app.core.tasks.engine import AsyncTaskDefinition
from app.services import novel as novel_service


async def clean_chapter_event_task(context: Any) -> dict[str, Any]:
    """批量章节事件清洗子任务处理器。"""
    payload = context.message.payload
    project_public_id = str(payload.get("project_public_id") or "").strip()
    current_user_public_id = str(payload.get("current_user_public_id") or "").strip()
    chapter_id = _payload_int(payload.get("chapter_id"))
    if not project_public_id or not current_user_public_id or chapter_id <= 0:
        raise ValueError("批量清洗章节事件任务参数不完整")

    chapter = await novel_service.clean_chapter(
        context.session,
        project_public_id,
        chapter_id,
        current_user_public_id,
    )
    return {
        "chapter_id": chapter.id,
        "chapter_public_id": chapter.public_id,
        "event_state": chapter.event_state,
        "event": chapter.event,
        "error_reason": chapter.error_reason,
    }


def _payload_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


ASYNC_TASKS = (
    AsyncTaskDefinition(novel_service.NOVEL_CHAPTER_CLEAN_TASK_TYPE, clean_chapter_event_task),
)
