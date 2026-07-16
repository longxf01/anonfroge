"""剧本创作 Agent 的单轮工具集。

每轮对话构建一次，闭包持有本轮 RAG 上下文、会话状态与章节事件数据。
update_project_config 直接改写会话状态的 workflow，变更随本轮对话提交持久化。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.services.screenwriting.project_config import (
    ensure_project_config,
    parse_source_chapter_range,
    update_project_config_from_message,
)
from app.services.screenwriting.rag_index import ScreenwritingRagContext
from app.services.screenwriting.rag_runtime import build_rag_tools
from app.services.screenwriting.state import ScreenwritingSessionState
from app.services.screenwriting.tool_prompts import apply_tool_descriptions


MAX_NOVEL_EVENT_RESULTS = 120


def build_screenwriting_agent_tools(
    rag_context: ScreenwritingRagContext,
    state: ScreenwritingSessionState,
    chapter_events: list[dict[str, Any]],
    chapter_index_range: tuple[int, int] | None,
) -> list[Callable[..., Any]]:
    """构建本轮 Agent 可用工具：RAG 检索 + 配置读写 + 工作区与章节事件读取。"""
    tools: list[Callable[..., Any]] = list(build_rag_tools(rag_context))

    def get_project_config() -> dict[str, str]:
        """读取当前创作配置（集数、单集时长、原著范围、平台规格、风格定位、付费策略）。"""
        return dict(ensure_project_config(state, chapter_index_range))

    def update_project_config(message: str) -> dict[str, str]:
        """根据用户的自然语言说明更新创作配置，返回更新后的完整配置。"""
        return dict(update_project_config_from_message(state, message, chapter_index_range))

    def get_workspace() -> dict[str, str]:
        """读取三个创作阶段工作区（故事骨架、改编策略、剧本草案）的当前完整内容。"""
        return {
            "activeTab": state.active_tab,
            "skeleton": state.workspace.skeleton,
            "strategy": state.workspace.strategy,
            "script": state.workspace.script,
        }

    def get_novel_events(start_chapter: int = 0, end_chapter: int = 0) -> dict[str, Any]:
        """按章节范围读取小说章节事件；不传范围时默认使用创作配置的原著范围。"""
        resolved_start = int(start_chapter or 0)
        resolved_end = int(end_chapter or 0)
        if resolved_start <= 0 or resolved_end <= 0:
            configured = parse_source_chapter_range(
                ensure_project_config(state, chapter_index_range).get("sourceRange", "")
            )
            if configured is not None:
                resolved_start, resolved_end = configured
        if resolved_start > 0 and resolved_end > 0 and resolved_start > resolved_end:
            resolved_start, resolved_end = resolved_end, resolved_start

        matched = [
            event
            for event in chapter_events
            if resolved_start <= 0
            or resolved_end <= 0
            or resolved_start <= int(event.get("chapterIndex", 0)) <= resolved_end
        ]
        return {
            "totalCount": len(matched),
            "truncated": len(matched) > MAX_NOVEL_EVENT_RESULTS,
            "events": matched[:MAX_NOVEL_EVENT_RESULTS],
        }

    tools.extend([get_project_config, update_project_config, get_workspace, get_novel_events])
    return apply_tool_descriptions(tools)