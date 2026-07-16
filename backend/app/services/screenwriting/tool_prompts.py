"""剧本创作工具相关提示词加载。

工具描述与提示词契约段外置在 data/script/ 目录（Markdown 文件），
供 web 端可视化编辑；文件缺失或为空时回退到内置兜底文本，保证主链路可用。
复用 PromptRegistry 的索引与缓存机制（文件 stem 即提示词名称）。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.core.config import Settings, script_prompts_root_path
from app.services.prompt_registry import PromptRegistry, PromptRegistryError


GUIDE_RUNTIME_CONTRACT_PROMPT = "guide_runtime_contract"
STAGE_RUNTIME_CONTRACT_PROMPT = "stage_runtime_contract"

# 内置兜底：与 data/script/ 下同名文件保持同义，文件缺失时使用。
SCRIPT_PROMPT_FALLBACKS: dict[str, str] = {
    "get_rag_context": "读取本轮剧本创作 RAG 检索上下文。",
    "get_project_config": "读取当前创作配置（集数、单集时长、原著范围、平台规格、风格定位、付费策略）。",
    "update_project_config": "根据用户的自然语言说明更新创作配置，返回更新后的完整配置。",
    "get_workspace": "读取三个创作阶段工作区（故事骨架、改编策略、剧本草案）的当前完整内容。",
    "get_novel_events": "按章节范围读取小说章节事件；不传范围时默认使用创作配置的原著范围。",
    GUIDE_RUNTIME_CONTRACT_PROMPT: (
        "可用工具：get_rag_context（检索项目资料）、get_project_config / update_project_config"
        "（读取与更新创作配置）、get_workspace（读取三阶段工作区全文）、"
        "get_novel_events（按章节范围读取小说章节事件）。\n"
        "当前能力边界：本轮支持多轮对话、上下文延续、项目资料检索与创作配置读写；"
        "阶段生成请求（故事骨架/改编策略/剧本草案）会由阶段助理直写右侧工作区。\n"
        "回答要求：使用简体中文，直接回应用户问题；如果本轮提供了项目资料检索上下文，"
        "必须优先依据其中的章节资料、人物信息或技能资料作答；资料不足时说明缺口，"
        "不要编造小说章节事件。"
    ),
    STAGE_RUNTIME_CONTRACT_PROMPT: (
        "数据来源：\"已确认创作配置\"是规格参数的唯一来源；\"配置章节事件\"是原著事实的"
        "唯一来源；以上数据已在运行时上下文中注入完整，直接依据其创作。\n"
        "硬性约束：章节范围、集数、单集时长、平台规格和付费策略必须严格匹配已确认创作配置；"
        "不得凭记忆编造章节事件、人物关系或情节因果。\n"
        "输出要求：只输出可直接写入右侧「{stage_label}」工作区的 Markdown 正文，"
        "不要输出确认语、工具调用说明、执行日志或代码栅栏包裹；"
        "输出必须聚焦{stage_label}，不要把其他阶段正文混入本阶段。"
    ),
}

_REGISTRY: PromptRegistry | None = None


def script_prompt_registry(config: Settings | None = None) -> PromptRegistry:
    """返回 data/script 提示词注册表（模块级缓存）。"""
    global _REGISTRY
    if _REGISTRY is None or config is not None:
        registry = PromptRegistry(script_prompts_root_path(config))
        if config is not None:
            return registry
        _REGISTRY = registry
    return _REGISTRY


def load_script_prompt(name: str, *, registry: PromptRegistry | None = None) -> str:
    """加载工具提示词；文件缺失或为空时回退内置兜底文本。"""
    prompt_registry = registry or script_prompt_registry()
    try:
        return prompt_registry.skill(name)
    except PromptRegistryError:
        return SCRIPT_PROMPT_FALLBACKS.get(name, "")


def stage_runtime_contract(stage_label: str, *, registry: PromptRegistry | None = None) -> str:
    """阶段提示词的工具/约束/输出契约段；{stage_label} 占位符替换为阶段名。"""
    template = load_script_prompt(STAGE_RUNTIME_CONTRACT_PROMPT, registry=registry)
    return template.replace("{stage_label}", stage_label)


def apply_tool_descriptions(
    tools: list[Callable[..., Any]],
    *,
    registry: PromptRegistry | None = None,
) -> list[Callable[..., Any]]:
    """按函数名从 data/script/tools/ 加载工具描述并覆盖 docstring。

    docstring 是 Agent 运行时暴露给模型的工具描述，外置后可在 web 端编辑。
    """
    for tool in tools:
        description = load_script_prompt(tool.__name__, registry=registry)
        if description:
            tool.__doc__ = description
    return tools