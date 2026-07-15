from __future__ import annotations

from app.schemas.screenwriting import ScreenwritingActiveTab
from app.services.prompt_registry import PromptRegistry, PromptRegistryError


GUIDE_ASSISTANT_PROMPT_NAME = "screenwriting_guide_assistant"

FALLBACK_GUIDE_ASSISTANT_PROMPT = (
    "你是剧本创作的 AI 引导助理。你负责和用户进行多轮对话，"
    "帮助用户澄清创作目标、说明当前创作阶段，并把后续阶段能力的边界讲清楚。"
)

ACTIVE_TAB_LABELS: dict[str, str] = {
    "skeleton": "故事骨架",
    "strategy": "改编策略",
    "script": "剧本",
}


def load_guide_assistant_prompt(registry: PromptRegistry | None = None) -> str:
    """从 data/skills 读取剧本创作引导助理提示词。"""
    prompt_registry = registry or PromptRegistry.from_settings()
    try:
        return prompt_registry.skill(GUIDE_ASSISTANT_PROMPT_NAME)
    except PromptRegistryError:
        return FALLBACK_GUIDE_ASSISTANT_PROMPT


def build_guide_system_prompt(active_tab: ScreenwritingActiveTab) -> str:
    """构建单次 Harness 对话的系统提示词。"""
    active_label = ACTIVE_TAB_LABELS.get(active_tab, "故事骨架")
    return (
        f"{load_guide_assistant_prompt()}\n\n"
        f"当前右侧活动阶段：{active_label}（{active_tab}）。\n"
        "阶段二能力边界：本轮只进行多轮对话和上下文延续；RAG 检索、阶段工作流切换、"
        "CrewAI 角色团队和右侧工作区写入会在后续阶段接入。\n"
        "回答要求：使用简体中文，直接回应用户问题；不要声称已经读取尚未接入的 RAG 资料，"
        "不要编造小说章节事件。"
    )
