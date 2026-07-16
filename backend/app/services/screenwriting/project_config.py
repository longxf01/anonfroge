"""剧本创作配置链路：草拟、抽取更新、查询应答与确认锁定。

创作配置（集数/单集时长/原著范围/平台规格/风格定位/付费策略）持久化在会话
workflow JSON 中，是后续故事骨架、改编策略与剧本生成阶段的唯一约束来源。
解析全部为确定性规则（正则 + 关键词），不依赖模型调用，保证低延迟与可测试性。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.screenwriting.constants import (
    GENERATION_KEYWORDS,
    STAGE_KEYWORDS,
    STAGE_ORDER,
    WORKFLOW_BASIC_INFO_CONFIRMED,
    WORKFLOW_PENDING_STAGE,
    WORKFLOW_PENDING_STAGE_MESSAGE,
    WORKFLOW_PROJECT_CONFIG,
)
from app.services.screenwriting.state import (
    ScreenwritingSessionState,
    stage_label,
)
from app.utils.time_tools import utc_now


CONFIRMATION_TOKENS: tuple[str, ...] = (
    "确认",
    "可以",
    "按以上",
    "按这个",
    "就这样",
    "同意",
    "开始",
    "继续",
    "ok",
    "okay",
    "yes",
    "confirm",
)

STYLE_TOKENS: tuple[str, ...] = ("爽剧", "甜宠", "复仇", "悬疑", "权谋", "都市", "古装")

CONFIG_FIELD_ROWS: tuple[tuple[str, str], ...] = (
    ("集数", "totalEpisodes"),
    ("单集时长", "episodeDuration"),
    ("原著范围", "sourceRange"),
    ("平台规格", "platformSpec"),
    ("风格定位", "style"),
    ("付费策略", "paywall"),
)


@dataclass(frozen=True)
class ProjectConfigDialogResult:
    """配置链路分流结果。

    reply 非空表示本轮由配置链路直接应答（不进入模型）；
    proceed_message 非空表示配置已确认，应以该消息继续正常 Agent 链路。
    """

    reply: str = ""
    proceed_message: str = ""


def draft_project_config(chapter_index_range: tuple[int, int] | None) -> dict[str, str]:
    """根据项目章节事件范围草拟默认创作配置。"""
    if chapter_index_range is not None:
        source_range = f"第{chapter_index_range[0]}-{chapter_index_range[1]}章"
    else:
        source_range = "待确认（当前项目尚无可用章节事件）"
    return {
        "totalEpisodes": "24集，可按你的目标调整",
        "episodeDuration": "2分钟/集，可按平台规格调整",
        "sourceRange": source_range,
        "platformSpec": "竖屏短剧优先，可改为横屏或其他规格",
        "style": "由故事骨架阶段结合小说事件细化，可指定爽剧、甜宠、复仇等方向",
        "paywall": "前3集免费，第4集起设置付费点，可按平台策略调整",
    }


def ensure_project_config(
    state: ScreenwritingSessionState,
    chapter_index_range: tuple[int, int] | None = None,
) -> dict[str, str]:
    """读取（必要时草拟并写入）当前创作配置。"""
    config = state.workflow.get(WORKFLOW_PROJECT_CONFIG)
    if not isinstance(config, dict):
        config = draft_project_config(chapter_index_range)
        state.workflow[WORKFLOW_PROJECT_CONFIG] = config
        state.updated_at = utc_now()
    return config


def update_project_config_from_message(
    state: ScreenwritingSessionState,
    message: str,
    chapter_index_range: tuple[int, int] | None = None,
) -> dict[str, str]:
    """从用户发言中确定性抽取配置项并合并到当前配置。"""
    config = ensure_project_config(state, chapter_index_range)
    updated = dict(config)
    text = message.strip()

    episode_match = re.search(r"(\d+)\s*集", text)
    if episode_match:
        updated["totalEpisodes"] = f"{episode_match.group(1)}集"

    duration_match = re.search(r"(\d+)\s*分钟", text)
    if duration_match:
        updated["episodeDuration"] = f"{duration_match.group(1)}分钟/集"

    range_match = re.search(r"第?\s*(\d+)\s*[-—到至]\s*(\d+)\s*章", text)
    if range_match:
        updated["sourceRange"] = f"第{range_match.group(1)}-{range_match.group(2)}章"

    platform_spec = _extract_platform_spec(text)
    if platform_spec:
        updated["platformSpec"] = platform_spec

    style_tokens = [token for token in STYLE_TOKENS if token in text]
    if style_tokens:
        updated["style"] = "、".join(style_tokens)

    if "免费" in text or "付费" in text:
        updated["paywall"] = _extract_labeled_config_value(text, ("付费策略", "付费", "免费")) or text

    updated["lastUserAdjustment"] = text
    state.workflow[WORKFLOW_PROJECT_CONFIG] = updated
    state.updated_at = utc_now()
    return updated


def format_project_config(config: object) -> str:
    """把配置渲染为面向用户的清单文本。"""
    if not isinstance(config, dict):
        return ""
    return "\n".join(
        f"- {label}：{config.get(key, '')}"
        for label, key in CONFIG_FIELD_ROWS
        if config.get(key, "")
    )


def parse_source_chapter_range(value: object) -> tuple[int, int] | None:
    """解析"第X-Y章"形式的原著范围；解析失败返回 None。"""
    text = str(value or "").strip()
    if not text:
        return None
    match = re.search(r"第?\s*(\d+)\s*[-—到至]\s*(\d+)\s*章", text)
    if not match:
        return None
    start = int(match.group(1))
    end = int(match.group(2))
    if start > end:
        start, end = end, start
    return start, end


def detect_stage_generation_request(message: str) -> str | None:
    """识别指向某个创作阶段的生成请求。

    "结合故事骨架，提出改编策略"这类引用前置阶段的句式中，意图阶段
    出现在句尾，因此按关键词最后出现位置取最靠后的阶段，而非首个命中。
    """
    text = message.strip()
    if not text:
        return None
    lowered = text.lower()
    if not any(keyword in lowered for keyword in GENERATION_KEYWORDS):
        return None
    best_stage: str | None = None
    best_position = -1
    for stage, keywords in STAGE_KEYWORDS:
        position = max(
            (lowered.rfind(keyword) for keyword in keywords if keyword in lowered),
            default=-1,
        )
        if position > best_position:
            best_position = position
            best_stage = stage
    return best_stage


def is_basic_info_confirmation(message: str) -> bool:
    text = message.strip().lower()
    if not text:
        return False
    return any(token in text for token in CONFIRMATION_TOKENS)


def resolve_project_config_dialog(
    state: ScreenwritingSessionState,
    message: str,
    chapter_index_range: tuple[int, int] | None = None,
) -> ProjectConfigDialogResult | None:
    """配置链路总分流：返回 None 表示与配置无关，走正常 Agent 链路。

    分流顺序：
    1. 存在待确认阶段：确认 → 锁定并以待执行消息继续；含配置要素 → 更新草案再次请确认。
    2. 阶段生成请求且配置未确认：草拟配置（合并消息中的要素）并请求确认。
    3. 配置更新请求：更新并回显。
    4. 配置查询请求：回显配置或单字段。
    """
    text = message.strip()
    if not text:
        return None

    pending_stage = state.workflow.get(WORKFLOW_PENDING_STAGE)
    pending_valid = isinstance(pending_stage, str) and pending_stage in STAGE_ORDER
    confirmed = state.workflow.get(WORKFLOW_BASIC_INFO_CONFIRMED) is True

    if pending_valid and not confirmed:
        if is_basic_info_confirmation(text):
            pending_message = str(state.workflow.get(WORKFLOW_PENDING_STAGE_MESSAGE) or text)
            confirm_basic_info(state, text)
            return ProjectConfigDialogResult(proceed_message=pending_message)
        if message_contains_project_config_hint(text):
            update_project_config_from_message(state, text, chapter_index_range)
            return ProjectConfigDialogResult(
                reply=(
                    "已根据你的说明更新创作配置草案：\n"
                    f"{format_project_config(state.workflow.get(WORKFLOW_PROJECT_CONFIG))}\n\n"
                    "如果认可该配置方案，请回复「确认」；仍需调整请继续告诉我。"
                )
            )
        return None

    requested_stage = detect_stage_generation_request(text)
    if requested_stage is not None and not confirmed:
        ensure_project_config(state, chapter_index_range)
        if message_contains_project_config_hint(text):
            update_project_config_from_message(state, text, chapter_index_range)
        state.workflow[WORKFLOW_PENDING_STAGE] = requested_stage
        state.workflow[WORKFLOW_PENDING_STAGE_MESSAGE] = text
        state.updated_at = utc_now()
        return ProjectConfigDialogResult(
            reply=_basic_info_confirmation_prompt(state, requested_stage)
        )

    if _is_project_config_update_request(text):
        update_project_config_from_message(state, text, chapter_index_range)
        return ProjectConfigDialogResult(
            reply=(
                "已根据你的说明更新当前项目创作配置：\n"
                f"{format_project_config(state.workflow.get(WORKFLOW_PROJECT_CONFIG))}"
            )
        )

    if _is_project_config_lookup_request(text):
        config = ensure_project_config(state, chapter_index_range)
        field = _project_config_field_from_message(text)
        if field is not None:
            label, key = field
            value = config.get(key) or "未设置"
            return ProjectConfigDialogResult(reply=f"当前项目配置的「{label}」是：{value}。")
        prefix = "当前项目创作配置如下："
        if not confirmed:
            prefix = "当前项目创作配置尚未确认，当前草案如下："
        return ProjectConfigDialogResult(reply=f"{prefix}\n{format_project_config(config)}")

    return None


def confirm_basic_info(state: ScreenwritingSessionState, message: str) -> None:
    """锁定创作配置并清理待确认阶段标记。"""
    state.workflow[WORKFLOW_BASIC_INFO_CONFIRMED] = True
    state.workflow["basicInfoConfirmation"] = message.strip()
    state.workflow.pop(WORKFLOW_PENDING_STAGE, None)
    state.workflow.pop(WORKFLOW_PENDING_STAGE_MESSAGE, None)
    state.updated_at = utc_now()


def message_contains_project_config_hint(message: str) -> bool:
    """判断发言是否包含可抽取的配置要素。"""
    text = message.strip()
    if not text:
        return False
    if re.search(r"第?\s*\d+\s*[-—到至]\s*\d+\s*章", text):
        return True
    if re.search(r"\d+\s*集", text):
        return True
    if re.search(r"\d+\s*分钟", text):
        return True
    if re.search(r"(16|9)\s*[:：]\s*(9|16)", text):
        return True
    return any(
        token in text
        for token in ("横屏", "竖屏", *STYLE_TOKENS, "付费", "免费")
    )


def _basic_info_confirmation_prompt(state: ScreenwritingSessionState, stage: str) -> str:
    config_block = format_project_config(state.workflow.get(WORKFLOW_PROJECT_CONFIG))
    label = stage_label(stage)
    return (
        f"好的，你现在需要创作「{label}」。在进入{label}阶段前，"
        "请先确认剧本基本信息和创作配置，确认后我再推进流程。\n\n"
        "当前项目的剧本基本信息和创作配置，建议配置如下：\n"
        f"{config_block}\n\n"
        "如果你认可该配置方案，请回复「确认」；如果需要调整，"
        "请直接把要修改的信息发给我，我会调整后再次请你确认。"
    )


def _is_project_config_update_request(message: str) -> bool:
    text = message.strip()
    if not text or not message_contains_project_config_hint(text):
        return False
    update_tokens = ("配置", "明确", "改为", "设置为", "调整为", "换成", "就是", "定为", "采用")
    return any(token in text for token in update_tokens)


def _is_project_config_lookup_request(message: str) -> bool:
    text = message.strip().lower()
    if not text:
        return False
    why_tokens = ("为什么", "为何", "原因", "理由", "依据")
    if any(token in text for token in why_tokens):
        return False
    config_tokens = (
        "配置",
        "项目配置",
        "创作配置",
        "剧本基本信息",
        "平台规格",
        "平台",
        "原著范围",
        "章节范围",
        "集数",
        "单集时长",
        "风格定位",
        "付费策略",
    )
    question_tokens = ("什么", "多少", "几", "当前", "查看", "读取", "显示", "是", "?", "？")
    return any(token in text for token in config_tokens) and any(token in text for token in question_tokens)


def _project_config_field_from_message(message: str) -> tuple[str, str] | None:
    text = message.strip().lower()
    fields = (
        ("平台规格", "platformSpec", ("平台规格", "平台", "横屏", "竖屏", "16:9", "9:16")),
        ("原著范围", "sourceRange", ("原著范围", "章节范围", "范围", "章节")),
        ("集数", "totalEpisodes", ("集数", "多少集", "几集")),
        ("单集时长", "episodeDuration", ("单集时长", "时长", "分钟")),
        ("风格定位", "style", ("风格定位", "风格", "类型")),
        ("付费策略", "paywall", ("付费策略", "付费", "免费", "付费点")),
    )
    for label, key, tokens in fields:
        if any(token in text for token in tokens):
            return label, key
    return None


def _extract_platform_spec(text: str) -> str:
    compact = re.sub(r"\s+", "", text)
    if "横屏" in compact:
        if re.search(r"16[:：]9|16比9", compact):
            return "16:9横屏"
        return "横屏剧集优先"
    if "竖屏" in compact:
        if re.search(r"9[:：]16|9比16", compact):
            return "9:16竖屏短剧优先"
        return "竖屏短剧优先"
    return ""


def _extract_labeled_config_value(text: str, labels: tuple[str, ...]) -> str:
    for raw_line in text.splitlines():
        line = raw_line.strip().lstrip("-*•").strip()
        if not line:
            continue
        for label in labels:
            match = re.match(rf"^{re.escape(label)}\s*[:：]\s*(.+)$", line)
            if match:
                return match.group(1).strip()
    return ""