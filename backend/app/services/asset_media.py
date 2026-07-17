from __future__ import annotations

"""资产图像媒体闭环服务。

负责：从结构化字段拼图像提示词、调用图像网关生成、落本地文件、写
AssetMedia/AssetGeneration、封面回写、列举与删除，以及图像生成异步任务的提交。

provider 级 generate_image 当前为接入桩；本服务以归一化的 MediaGenerationOutput
为契约，真实出图只需在对应 provider 填实现，无需改动本服务。
"""

import base64
import json
import re
from pathlib import Path
from time import perf_counter
from typing import Any

import httpx
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import BASE_DIR, settings
from app.models.asset import (
    ASSET_RELATION_CHILD_OF,
    ASSET_GENERATION_STATUS_FAILED,
    ASSET_GENERATION_STATUS_RUNNING,
    ASSET_GENERATION_STATUS_SUCCEEDED,
    ASSET_GENERATION_TYPE_IMAGE,
    ASSET_MEDIA_ROLE_FINAL,
    ASSET_MEDIA_ROLE_GENERATED,
    ASSET_MEDIA_ROLE_REFERENCE,
    ASSET_MEDIA_TYPE_IMAGE,
    Asset,
    AssetGeneration,
    AssetMedia,
    AssetRelation,
)
from app.schemas.tasks import TaskItemCreate, TaskJobCreate, TaskJobDetail
from app.services import asset as asset_service
from app.services import project as project_service
from app.services.agent_gateway import (
    MediaGenerationOutput,
    ProviderModelGateway,
    ProviderModelGatewayError,
)
from app.services.prompt_registry import PromptRegistry, PromptRegistryError
from app.utils.time_tools import utc_now


ASSET_IMAGE_PROMPT_TASK_TYPE = "asset.image_prompt"
ASSET_IMAGE_GENERATION_TASK_TYPE = "asset.image_generation"

_MIME_EXT = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/webp": "webp",
    "image/gif": "gif",
}
_REFERENCE_IMAGE_MIME_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/webp"}
_REFERENCE_IMAGE_MAX_BYTES = 20 * 1024 * 1024

_STYLE_PATH_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,119}$")


class _MediaTiming:
    """收集资产媒体各阶段的服务端耗时。"""

    def __init__(self) -> None:
        self.started_at = perf_counter()
        self.stages: list[dict[str, int | str]] = []

    def mark(self, name: str, started_at: float, ended_at: float | None = None) -> None:
        ended_at = ended_at if ended_at is not None else perf_counter()
        self.stages.append(
            {
                "name": name,
                "durationMs": _duration_ms(started_at, ended_at),
                "startedAtMs": _duration_ms(self.started_at, started_at),
                "endedAtMs": _duration_ms(self.started_at, ended_at),
            }
        )

    def payload(self) -> dict[str, Any]:
        return {
            "totalMs": _duration_ms(self.started_at, perf_counter()),
            "stages": [dict(stage) for stage in self.stages],
        }


def _duration_ms(started_at: float, ended_at: float) -> int:
    return max(0, int((ended_at - started_at) * 1000))


def build_media_gateway() -> ProviderModelGateway:
    """构建图像媒体网关，便于测试替换。"""

    return ProviderModelGateway(timeout=settings.image_generation_timeout_seconds)


# ---------------------------------------------------------------------------
# 提示词与字节归一
# ---------------------------------------------------------------------------

def load_asset_image_prompt(registry: PromptRegistry | None = None) -> str:
    """从 data/skills 读取资产生图专业提示词合成提示词。"""

    prompt_name = settings.asset_image_prompt_name.strip()
    if not prompt_name:
        raise asset_service.AssetServiceError("资产生图提示词名称未配置")
    prompt_registry = registry or PromptRegistry.from_settings()
    try:
        return prompt_registry.skill(prompt_name)
    except PromptRegistryError as exc:
        raise asset_service.AssetServiceError(str(exc)) from exc


def build_asset_image_prompt(asset: Asset) -> str:
    """从资产结构化字段拼接题材中立的图像生成提示词。"""

    parts: list[str] = []
    name = (asset.name or "").strip()
    if name:
        parts.append(name)
    summary = (asset.summary or "").strip()
    if summary:
        parts.append(summary)
    for field_name in ("description", "details", "accessories"):
        mapping = asset_service._parse_object_field(getattr(asset, field_name))
        rendered = "，".join(
            f"{key}：{value}" for key, value in mapping.items() if str(value or "").strip()
        )
        if rendered:
            parts.append(rendered)
    colors = (asset.colors or "").strip()
    if colors:
        parts.append(f"色彩：{colors}")
    keyword = (asset.keyword or "").strip()
    if keyword:
        parts.append(f"风格：{keyword}")
    return "。".join(parts).strip()


def _build_derivative_edit_prompt(prompt: str, *, asset: Asset, reference_count: int) -> str:
    """为衍生资产编辑图补充父级参考图一致性约束。"""

    base_prompt = (prompt or "").strip()
    name = (asset.name or "").strip()
    variant_label = (asset.variant_label or "").strip()
    summary = (asset.summary or "").strip()
    asset_bits = [item for item in (name, variant_label, summary) if item]
    asset_context = "；".join(asset_bits) if asset_bits else "当前衍生资产"
    count_text = max(1, int(reference_count))

    return (
        "你正在基于父级参考图生成同一资产的衍生状态图。"
        f"已提供 {count_text} 张父级参考图，这些图片是强约束，不是普通灵感参考。\n\n"
        "必须保留父级参考图中的主体身份、物体结构或场景布局，以及五官/脸型、体型比例、发型、"
        "服装轮廓、配饰、主色、材质、构图语言和整体画风的一致性。\n"
        "只允许根据当前衍生资产描述调整变体差异，例如表情、姿态、伤痕、战损、服装细节、"
        "道具状态、年龄阶段或环境状态。不要创建全新角色、全新物体或无关场景。\n"
        "当文字描述与父级参考图冲突时，以父级参考图的视觉身份和设定为准，文字只用于表达衍生差异。\n\n"
        f"当前衍生资产：{asset_context}\n\n"
        f"当前衍生资产提示词：\n{base_prompt}"
    ).strip()


def _image_edit_parameters_for_model(model_id: str) -> dict[str, Any]:
    """返回当前模型适用的图片编辑增强参数。"""

    normalized = (model_id or "").strip().lower()
    if normalized == "gpt-image-1" or normalized.startswith("gpt-image-1-") or normalized.startswith("gpt-image-1."):
        return {"input_fidelity": "high"}
    return {}


def _asset_prompt_payload(asset: Asset) -> dict[str, Any]:
    """把资产结构化字段整理为提示词合成输入。"""

    return {
        "assetType": asset.asset_type,
        "name": asset.name,
        "summary": asset.summary or "",
        "keyword": asset.keyword or "",
        "colors": asset.colors or "",
        "description": asset_service._parse_object_field(asset.description),
        "details": asset_service._parse_object_field(asset.details),
        "accessories": asset_service._parse_object_field(asset.accessories),
    }


def _target_sheet_label(asset_type: str) -> str:
    """按资产类型给出设定图目标。"""

    if asset_type == "scene":
        return "场景四视图设定图"
    if asset_type == "role":
        return "人物三视图设定图"
    if asset_type == "prop":
        return "道具多视图设定图"
    if asset_type == "faction":
        return "势力视觉设定图"
    return "资产设定图"


def _strip_prompt_fence(text: str) -> str:
    """清理模型偶发输出的代码围栏，只保留提示词文本。"""

    value = (text or "").strip()
    fenced = re.fullmatch(r"```(?:text|markdown|md)?\s*(.*?)```", value, re.DOTALL)
    if fenced:
        value = fenced.group(1).strip()
    return value


def _resolve_art_style_text(project: Any) -> str:
    """读取项目 art_style 对应视觉风格 Markdown 内容；缺失或非法时返回空文本。"""

    style_path = str(getattr(project, "art_style", "") or "").strip()
    if not style_path or not _STYLE_PATH_PATTERN.fullmatch(style_path) or style_path in {".", ".."}:
        return ""
    configured = Path(settings.visual_style_root).expanduser()
    root = configured if configured.is_absolute() else BASE_DIR / configured
    root = root.resolve()
    style_dir = (root / style_path).resolve()
    try:
        style_dir.relative_to(root)
    except ValueError:
        return ""
    if not style_dir.is_dir():
        return ""
    contents: list[str] = []
    readme = style_dir / "README.md"
    paths = [readme] if readme.is_file() else []
    paths.extend(path for path in sorted(style_dir.glob("*.md")) if path.is_file() and path != readme)
    for path in paths:
        try:
            content = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if content:
            contents.append(f"## {path.name}\n{content}")
    return "\n\n".join(contents)


def build_asset_image_prompt_messages(
    *,
    asset: Asset,
    image_model_id: str,
    art_style_id: str,
    art_style_text: str,
) -> list[dict[str, str]]:
    """构建资产生图专业提示词合成消息。"""

    system = load_asset_image_prompt()
    asset_block = json.dumps(_asset_prompt_payload(asset), ensure_ascii=False, indent=2)
    user = (
        f"## 输出目标\n{_target_sheet_label(asset.asset_type)}\n\n"
        f"## 图像模型ID：{image_model_id}\n\n"
        f"## 艺术风格ID：{art_style_id or '未配置'}\n\n"
        f"## 艺术风格手册\n{art_style_text.strip() or '（未找到艺术风格手册）'}\n\n"
        f"## 当前资产结构化信息\n{asset_block}\n\n"
        "请只输出一条可直接提交给图像模型的专业正向提示词文本。"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


async def synthesize_asset_image_prompt(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    *,
    asset_public_id: str,
    gateway: Any | None = None,
) -> str:
    """使用项目绑定文本模型，为单个资产合成专业生图提示词。"""

    result = await synthesize_asset_image_prompt_detail(
        session,
        project_public_id,
        user_public_id,
        asset_public_id=asset_public_id,
        gateway=gateway,
    )
    return str(result.get("prompt") or "")


async def synthesize_asset_image_prompt_detail(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    *,
    asset_public_id: str,
    gateway: Any | None = None,
) -> dict[str, Any]:
    """使用项目绑定文本模型，为单个资产合成专业生图提示词并返回诊断信息。"""

    timing = _MediaTiming()
    stage_started_at = perf_counter()
    project = await project_service.get_project_or_raise(session, project_public_id, user_public_id)
    timing.mark("project_lookup", stage_started_at)
    text_model_id = str(project.text_model or "").strip()
    image_model_id = str(project.image_model or "").strip()
    if not text_model_id:
        raise asset_service.AssetServiceError("项目未绑定文本模型，请先在项目设置中选择文本模型")
    if not image_model_id:
        raise asset_service.AssetServiceError("项目未绑定图像模型，请先在项目设置中选择图像模型")

    stage_started_at = perf_counter()
    asset = await asset_service.load_asset_or_raise(session, int(project.id), user_public_id, asset_public_id)
    timing.mark("asset_lookup", stage_started_at)

    stage_started_at = perf_counter()
    art_style_id = str(project.art_style or "").strip()
    messages = build_asset_image_prompt_messages(
        asset=asset,
        image_model_id=image_model_id,
        art_style_id=art_style_id,
        art_style_text=_resolve_art_style_text(project),
    )
    prompt_trace = asset_service._model_prompt_trace(model_id=text_model_id, messages=messages)
    timing.mark("prompt_build", stage_started_at)

    resolved_gateway = gateway or asset_service.build_asset_gateway()
    try:
        stage_started_at = perf_counter()
        output = await asset_service._generate_full_text(resolved_gateway, model_id=text_model_id, messages=messages)
        timing.mark("prompt_model", stage_started_at)
    except ProviderModelGatewayError as exc:
        timing.mark("prompt_model", stage_started_at)
        raise asset_service.AssetServiceError(
            f"资产生图提示词合成失败：{exc}",
            result={
                **prompt_trace,
                "asset_public_id": asset_public_id,
                "image_model_id": image_model_id,
                "art_style_id": art_style_id,
                "asset_timing": timing.payload(),
            },
        ) from exc

    stage_started_at = perf_counter()
    prompt = _strip_prompt_fence(output)
    timing.mark("prompt_parse", stage_started_at)
    result = {
        **prompt_trace,
        "asset_public_id": asset_public_id,
        "asset_name": asset.name,
        "model_id": text_model_id,
        "image_model_id": image_model_id,
        "art_style_id": art_style_id,
        "prompt": prompt,
        "raw_output": output,
        "output_text": prompt,
        "asset_timing": timing.payload(),
    }
    if not prompt:
        raise asset_service.AssetServiceError("资产生图提示词合成结果为空", result=result)
    return result


def _strip_data_uri(value: str) -> str:
    text = value.strip()
    if text.startswith("data:") and "," in text:
        return text.split(",", 1)[1]
    return text


async def _resolve_media_bytes(output: MediaGenerationOutput) -> bytes:
    """把媒体结果归一为字节：data > b64 > url 下载。"""

    if output.data:
        return output.data
    if output.b64:
        try:
            return base64.b64decode(_strip_data_uri(output.b64))
        except (ValueError, TypeError) as exc:
            raise asset_service.AssetServiceError("图像 base64 解码失败") from exc
    if output.url:
        try:
            async with httpx.AsyncClient(timeout=settings.image_generation_timeout_seconds) as client:
                response = await client.get(output.url)
                response.raise_for_status()
                return response.content
        except httpx.HTTPError as exc:
            raise asset_service.AssetServiceError(f"下载生成图像失败：{exc}") from exc
    raise asset_service.AssetServiceError("生成结果不含可用图像数据")


# ---------------------------------------------------------------------------
# 本地存储与内容 URL
# ---------------------------------------------------------------------------

def _asset_media_root() -> Path:
    configured = Path(settings.asset_media_root).expanduser()
    root = configured if configured.is_absolute() else BASE_DIR / configured
    return root.resolve()


def _content_url(project_public_id: str, media_public_id: str) -> str:
    """构建可直接给浏览器 <img src> 的内容访问 URL。"""

    api_prefix = settings.api_prefix.strip()
    if api_prefix and not api_prefix.startswith("/"):
        api_prefix = f"/{api_prefix}"
    api_prefix = api_prefix.rstrip("/")
    return f"{api_prefix}/projects/{project_public_id}/assets/media/{media_public_id}/content"


def _ext_for(mime: str, url: str) -> str:
    ext = _MIME_EXT.get((mime or "").strip().lower())
    if ext:
        return ext
    tail = url.rsplit(".", 1)[-1].lower() if "." in url else ""
    if tail in {"png", "jpg", "jpeg", "webp", "gif"}:
        return "jpg" if tail == "jpeg" else tail
    return "png"


def _store_image_bytes(
    *, project_public_id: str, asset_public_id: str, media_public_id: str, data: bytes, ext: str
) -> str:
    """把图片字节写入本地存储，返回相对 storage_key。"""

    root = _asset_media_root()
    rel = Path(project_public_id) / asset_public_id / f"{media_public_id}.{ext}"
    target = (root / rel).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise asset_service.AssetServiceError("非法的媒体存储路径") from exc
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return rel.as_posix()


def media_abs_path(storage_key: str) -> Path | None:
    """把 storage_key 解析为存储根内的绝对路径；非法或越界返回 None。"""

    key = (storage_key or "").strip().lstrip("/\\")
    if not key:
        return None
    root = _asset_media_root()
    target = (root / key).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        return None
    return target


# ---------------------------------------------------------------------------
# 媒体加载
# ---------------------------------------------------------------------------

async def _load_media_or_raise(
    session: AsyncSession, project_id: int, user_public_id: str, media_public_id: str
) -> AssetMedia:
    statement = select(AssetMedia).where(
        AssetMedia.public_id == media_public_id,
        AssetMedia.project_id == project_id,
        AssetMedia.user_public_id == user_public_id,
        AssetMedia.disabled_at.is_(None),
    )
    media = (await session.exec(statement)).first()
    if media is None:
        raise asset_service.AssetNotFoundError("媒体不存在或无权访问")
    return media


def _dedupe_text_list(values: list[str] | None) -> list[str]:
    """清理字符串列表并保持顺序去重。"""

    if not isinstance(values, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


async def _load_reference_media_files(
    session: AsyncSession,
    *,
    project_id: int,
    user_public_id: str,
    media_public_ids: list[str],
) -> list[dict[str, Any]]:
    """读取任务引用的本地参考图，供 images/edits multipart 调用。"""

    images: list[dict[str, Any]] = []
    for media_public_id in _dedupe_text_list(media_public_ids):
        media = await _load_media_or_raise(session, project_id, user_public_id, media_public_id)
        if media.media_type != ASSET_MEDIA_TYPE_IMAGE:
            raise asset_service.AssetServiceError("参考媒体必须是图片")
        path = media_abs_path(media.storage_key)
        if path is None or not path.exists():
            raise asset_service.AssetNotFoundError("参考图文件不存在")
        mime_type = (media.mime_type or "image/png").strip().lower()
        if mime_type not in _REFERENCE_IMAGE_MIME_TYPES:
            raise asset_service.AssetServiceError("参考图仅支持 PNG/JPEG/WebP")
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise asset_service.AssetServiceError(f"读取参考图失败：{exc}") from exc
        if not data:
            raise asset_service.AssetServiceError("参考图内容为空")
        images.append(
            {
                "media_public_id": media.public_id,
                "filename": path.name,
                "mime_type": mime_type,
                "data": data,
            }
        )
    return images


async def _parent_asset_id_for(
    session: AsyncSession,
    *,
    asset_id: int,
) -> int | None:
    """查找衍生资产绑定的主资产 ID。"""

    relation = (
        await session.exec(
            select(AssetRelation).where(
                AssetRelation.source_asset_id == asset_id,
                AssetRelation.relation_type == ASSET_RELATION_CHILD_OF,
            )
        )
    ).first()
    if relation is None:
        return None
    try:
        return int(relation.target_asset_id)
    except (TypeError, ValueError):
        return None


async def _latest_asset_image_media_public_ids(
    session: AsyncSession,
    *,
    project_id: int,
    user_public_id: str,
    asset_id: int,
) -> list[str]:
    """取指定资产可作为编辑参考的图片媒体，封面优先，其次最近生成图。"""

    rows = (
        await session.exec(
            select(AssetMedia)
            .where(
                AssetMedia.project_id == project_id,
                AssetMedia.asset_id == asset_id,
                AssetMedia.user_public_id == user_public_id,
                AssetMedia.media_type == ASSET_MEDIA_TYPE_IMAGE,
                AssetMedia.media_role != ASSET_MEDIA_ROLE_REFERENCE,
                AssetMedia.disabled_at.is_(None),
            )
            .order_by(AssetMedia.created_at.desc(), AssetMedia.id.desc())
        )
    ).all()
    if not rows:
        return []
    cover = next((media for media in rows if media.media_role == ASSET_MEDIA_ROLE_FINAL), None)
    return [(cover or rows[0]).public_id]


async def get_media_file(session: AsyncSession, media_public_id: str) -> tuple[Path, str]:
    """按公开 ID 取媒体本地文件路径与 MIME（供内容路由公开服务，uuid 即访问凭据）。"""

    media = (
        await session.exec(
            select(AssetMedia).where(
                AssetMedia.public_id == media_public_id,
                AssetMedia.disabled_at.is_(None),
            )
        )
    ).first()
    if media is None:
        raise asset_service.AssetNotFoundError("媒体不存在")
    path = media_abs_path(media.storage_key)
    if path is None or not path.exists():
        raise asset_service.AssetNotFoundError("媒体文件不存在")
    return path, (media.mime_type or "application/octet-stream")


async def upload_asset_reference_image(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    *,
    asset_public_id: str,
    filename: str,
    content_type: str,
    data: bytes,
) -> AssetMedia:
    """上传本地参考图并保存为资产 reference 媒体。"""

    mime_type = (content_type or "").split(";", 1)[0].strip().lower()
    if mime_type not in _REFERENCE_IMAGE_MIME_TYPES:
        raise asset_service.AssetServiceError("参考图仅支持 PNG/JPEG/WebP")
    if not data:
        raise asset_service.AssetServiceError("参考图内容为空")
    if len(data) > _REFERENCE_IMAGE_MAX_BYTES:
        raise asset_service.AssetServiceError("参考图过大，最大支持 20MB")

    project = await project_service.get_project_or_raise(session, project_public_id, user_public_id)
    asset = await asset_service.load_asset_or_raise(session, int(project.id), user_public_id, asset_public_id)
    media = AssetMedia(
        project_id=int(project.id),
        user_public_id=user_public_id,
        asset_id=int(asset.id),
        media_type=ASSET_MEDIA_TYPE_IMAGE,
        media_role=ASSET_MEDIA_ROLE_REFERENCE,
        mime_type=mime_type,
        prompt="",
        extra_data=json.dumps({"source": "upload", "filename": filename}, ensure_ascii=False),
    )
    session.add(media)
    await session.flush()

    storage_key = _store_image_bytes(
        project_public_id=project_public_id,
        asset_public_id=asset_public_id,
        media_public_id=media.public_id,
        data=data,
        ext=_ext_for(mime_type, filename),
    )
    media.storage_key = storage_key
    media.url = _content_url(project_public_id, media.public_id)
    session.add(media)
    await session.flush()
    return media


# ---------------------------------------------------------------------------
# 生成 / 封面 / 列举 / 删除
# ---------------------------------------------------------------------------

async def generate_asset_image(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    *,
    asset_public_id: str,
    model_id: str,
    prompt: str = "",
    aspect_ratio: str = "",
    image_size: str = "",
    reference_media_public_ids: list[str] | None = None,
    make_cover: bool = True,
    task_job_public_id: str = "",
    task_item_public_id: str = "",
    gateway: Any | None = None,
) -> dict[str, Any]:
    """为单个资产生成图像：写生成记录 → 调网关 → 落盘 → 写媒体 → 设封面。"""

    timing = _MediaTiming()
    stage_started_at = perf_counter()
    project = await project_service.get_project_or_raise(session, project_public_id, user_public_id)
    timing.mark("project_lookup", stage_started_at)
    model_id = str(model_id or project.image_model or "").strip()
    if not model_id:
        raise asset_service.AssetServiceError("项目未绑定图像模型，请先在项目设置中选择图像模型")

    stage_started_at = perf_counter()
    asset = await asset_service.load_asset_or_raise(session, int(project.id), user_public_id, asset_public_id)
    timing.mark("asset_lookup", stage_started_at)

    resolved_gateway = gateway or build_media_gateway()
    final_prompt = (prompt or "").strip()
    prompt_trace: dict[str, Any] = {
        "model_id": model_id,
        "messages": [],
        "composed_prompt": final_prompt,
        "prompt": final_prompt,
    }
    if not final_prompt:
        stage_started_at = perf_counter()
        prompt_result = await synthesize_asset_image_prompt_detail(
            session,
            project_public_id,
            user_public_id,
            asset_public_id=asset_public_id,
        )
        final_prompt = str(prompt_result.get("prompt") or "").strip()
        prompt_trace = {
            "model_id": model_id,
            "messages": prompt_result.get("messages") or [],
            "composed_prompt": str(prompt_result.get("composed_prompt") or ""),
            "prompt": final_prompt,
            "prompt_model_id": str(prompt_result.get("model_id") or ""),
            "image_model_id": str(prompt_result.get("image_model_id") or model_id),
        }
        timing.mark("prompt_synthesis", stage_started_at)
    if not final_prompt:
        raise asset_service.AssetServiceError(
            "资产信息不足以生成图像提示词",
            result={**prompt_trace, "asset_public_id": asset_public_id, "asset_timing": timing.payload()},
        )

    is_derivative_asset = not bool(getattr(asset, "main_asset", False))
    reference_media_ids = [] if not is_derivative_asset else _dedupe_text_list(reference_media_public_ids)
    if is_derivative_asset and not reference_media_ids:
        stage_started_at = perf_counter()
        parent_asset_id = await _parent_asset_id_for(session, asset_id=int(asset.id))
        if parent_asset_id is None:
            raise asset_service.AssetServiceError(
                "衍生资产需要先绑定主资产，再生成衍生图",
                result={**prompt_trace, "asset_public_id": asset_public_id, "asset_timing": timing.payload()},
            )
        reference_media_ids = await _latest_asset_image_media_public_ids(
            session,
            project_id=int(project.id),
            user_public_id=user_public_id,
            asset_id=parent_asset_id,
        )
        timing.mark("parent_reference_media", stage_started_at)
        if not reference_media_ids:
            raise asset_service.AssetServiceError(
                "请先为主资产生成配图，再生成衍生资产图",
                result={**prompt_trace, "asset_public_id": asset_public_id, "asset_timing": timing.payload()},
            )
    reference_images: list[dict[str, Any]] = []
    if reference_media_ids:
        stage_started_at = perf_counter()
        reference_images = await _load_reference_media_files(
            session,
            project_id=int(project.id),
            user_public_id=user_public_id,
            media_public_ids=reference_media_ids,
        )
        timing.mark("reference_media", stage_started_at)
        if not reference_images:
            raise asset_service.AssetServiceError(
                "请选择至少一张参考图",
                result={**prompt_trace, "asset_public_id": asset_public_id, "asset_timing": timing.payload()},
            )

    model_prompt = final_prompt
    edit_parameters = _image_edit_parameters_for_model(model_id) if reference_images else {}
    if reference_images and is_derivative_asset:
        model_prompt = _build_derivative_edit_prompt(
            final_prompt,
            asset=asset,
            reference_count=len(reference_images),
        )
        prompt_trace = {
            **prompt_trace,
            "base_prompt": final_prompt,
            "prompt": model_prompt,
            "reference_prompt_mode": "derivative_edit",
        }

    stage_started_at = perf_counter()
    generation_mode = "edit" if reference_images else "generate"
    generation = AssetGeneration(
        project_id=int(project.id),
        user_public_id=user_public_id,
        asset_id=int(asset.id),
        generation_type=ASSET_GENERATION_TYPE_IMAGE,
        model_id=model_id,
        prompt=model_prompt,
        parameters=json.dumps(
            {
                "aspect_ratio": aspect_ratio.strip(),
                "image_size": image_size.strip(),
                "mode": generation_mode,
                "reference_media_public_ids": reference_media_ids,
                **edit_parameters,
            },
            ensure_ascii=False,
        ),
        status=ASSET_GENERATION_STATUS_RUNNING,
        task_job_public_id=task_job_public_id.strip(),
        task_item_public_id=task_item_public_id.strip(),
        started_at=utc_now(),
    )
    session.add(generation)
    await session.flush()
    timing.mark("generation_record", stage_started_at)

    gen_kwargs: dict[str, Any] = {}
    if aspect_ratio.strip():
        gen_kwargs["aspect_ratio"] = aspect_ratio.strip()
    if image_size.strip():
        gen_kwargs["image_size"] = image_size.strip()
    try:
        stage_started_at = perf_counter()
        if reference_images:
            output = await resolved_gateway.edit_image(
                model_id=model_id,
                prompt=model_prompt,
                images=reference_images,
                **edit_parameters,
                **gen_kwargs,
            )
        else:
            output = await resolved_gateway.generate_image(model_id=model_id, prompt=model_prompt, **gen_kwargs)
        timing.mark("image_model", stage_started_at)
        stage_started_at = perf_counter()
        data = await _resolve_media_bytes(output)
        timing.mark("media_bytes", stage_started_at)
    except (ProviderModelGatewayError, asset_service.AssetServiceError) as exc:
        generation.status = ASSET_GENERATION_STATUS_FAILED
        generation.error_message = str(exc)
        generation.completed_at = utc_now()
        session.add(generation)
        await session.flush()
        raise asset_service.AssetServiceError(
            f"图像生成失败：{exc}",
            result={
                **prompt_trace,
                "asset_public_id": asset_public_id,
                "generation_public_id": generation.public_id,
                "asset_timing": timing.payload(),
            },
        ) from exc

    stage_started_at = perf_counter()
    media = AssetMedia(
        project_id=int(project.id),
        user_public_id=user_public_id,
        asset_id=int(asset.id),
        media_type=ASSET_MEDIA_TYPE_IMAGE,
        media_role=ASSET_MEDIA_ROLE_GENERATED,
        mime_type=output.mime_type or "image/png",
        width=output.width,
        height=output.height,
        prompt=model_prompt,
        generation_public_id=generation.public_id,
    )
    session.add(media)
    await session.flush()

    storage_key = _store_image_bytes(
        project_public_id=project_public_id,
        asset_public_id=asset_public_id,
        media_public_id=media.public_id,
        data=data,
        ext=_ext_for(media.mime_type, output.url),
    )
    media.storage_key = storage_key
    media.url = _content_url(project_public_id, media.public_id)
    session.add(media)

    output_summary = {
        "media_public_id": media.public_id,
        "url": media.url,
        "mime_type": media.mime_type,
        "width": media.width,
        "height": media.height,
        "duration_ms": output.duration_ms,
        "seed": output.seed,
        "usage": output.usage,
        "cost": output.cost,
        "mode": generation_mode,
        "reference_media_public_ids": reference_media_ids,
    }
    generation.status = ASSET_GENERATION_STATUS_SUCCEEDED
    generation.completed_at = utc_now()
    generation.output = json.dumps(output_summary, ensure_ascii=False)
    session.add(generation)
    await session.flush()
    timing.mark("media_write", stage_started_at)

    if make_cover:
        stage_started_at = perf_counter()
        existing_cover = (
            await session.exec(
                select(AssetMedia).where(
                    AssetMedia.asset_id == int(asset.id),
                    AssetMedia.media_role == ASSET_MEDIA_ROLE_FINAL,
                    AssetMedia.public_id != media.public_id,
                    AssetMedia.disabled_at.is_(None),
                )
            )
        ).first()
        if existing_cover is None:
            await _set_cover_media(session, asset_id=int(asset.id), media=media)
        timing.mark("cover_update", stage_started_at)

    output_text = json.dumps(output_summary, ensure_ascii=False)
    return {
        "media": media,
        "generation": generation,
        **prompt_trace,
        "model_id": model_id,
        "asset_public_id": asset_public_id,
        "media_public_id": media.public_id,
        "generation_public_id": generation.public_id,
        "reference_media_public_ids": reference_media_ids,
        "url": media.url,
        "raw_output": output_text,
        "output_text": output_text,
        "asset_timing": timing.payload(),
    }


async def _set_cover_media(session: AsyncSession, *, asset_id: int, media: AssetMedia) -> None:
    """把指定 media 设为资产封面（media_role=final），同资产其它封面降级。"""

    existing = (
        await session.exec(
            select(AssetMedia).where(
                AssetMedia.asset_id == asset_id,
                AssetMedia.media_role == ASSET_MEDIA_ROLE_FINAL,
            )
        )
    ).all()
    for item in existing:
        if item.public_id != media.public_id:
            item.media_role = ASSET_MEDIA_ROLE_GENERATED
            session.add(item)
    media.media_role = ASSET_MEDIA_ROLE_FINAL
    session.add(media)
    await session.flush()


async def set_asset_cover(
    session: AsyncSession, project_public_id: str, user_public_id: str, media_public_id: str
) -> AssetMedia:
    """把指定媒体设为其所属资产的封面。"""

    project = await project_service.get_project_or_raise(session, project_public_id, user_public_id)
    media = await _load_media_or_raise(session, int(project.id), user_public_id, media_public_id)
    await _set_cover_media(session, asset_id=int(media.asset_id), media=media)
    return media


async def list_asset_media(
    session: AsyncSession, project_public_id: str, user_public_id: str, asset_public_id: str
) -> list[AssetMedia]:
    """列出某资产的媒体，按创建时间倒序。"""

    project = await project_service.get_project_or_raise(session, project_public_id, user_public_id)
    asset = await asset_service.load_asset_or_raise(session, int(project.id), user_public_id, asset_public_id)
    statement = (
        select(AssetMedia)
        .where(
            AssetMedia.asset_id == int(asset.id),
            AssetMedia.user_public_id == user_public_id,
            AssetMedia.disabled_at.is_(None),
        )
        .order_by(AssetMedia.created_at.desc(), AssetMedia.id.desc())
    )
    return list((await session.exec(statement)).all())


async def delete_asset_media(
    session: AsyncSession, project_public_id: str, user_public_id: str, media_public_id: str
) -> None:
    """删除单个媒体：删 DB 行并清理本地文件。"""

    project = await project_service.get_project_or_raise(session, project_public_id, user_public_id)
    media = await _load_media_or_raise(session, int(project.id), user_public_id, media_public_id)
    _unlink_storage_key(media.storage_key)
    await session.delete(media)
    await session.flush()


def _unlink_storage_key(storage_key: str) -> None:
    path = media_abs_path(storage_key)
    if path and path.exists():
        try:
            path.unlink()
        except OSError:
            pass


async def delete_media_files_for_asset_ids(session: AsyncSession, asset_ids: list[int]) -> None:
    """删除一组资产的全部媒体本地文件（用于级联删除前的文件清理）。"""

    if not asset_ids:
        return
    rows = (await session.exec(select(AssetMedia).where(AssetMedia.asset_id.in_(asset_ids)))).all()
    for media in rows:
        _unlink_storage_key(media.storage_key)


async def cover_urls_for(
    session: AsyncSession, project_id: int, user_public_id: str, assets: list[Asset]
) -> dict[str, str]:
    """批量取每个资产的封面 url（final 优先，回退最近一张图像），避免 N+1。"""

    result: dict[str, str] = {}
    asset_ids = [int(a.id) for a in assets if a.id is not None]
    if not asset_ids:
        return result
    id_to_public = {int(a.id): a.public_id for a in assets if a.id is not None}
    rows = (
        await session.exec(
            select(AssetMedia)
            .where(
                AssetMedia.asset_id.in_(asset_ids),
                AssetMedia.media_type == ASSET_MEDIA_TYPE_IMAGE,
                AssetMedia.media_role != ASSET_MEDIA_ROLE_REFERENCE,
                AssetMedia.user_public_id == user_public_id,
                AssetMedia.disabled_at.is_(None),
            )
            .order_by(AssetMedia.created_at.desc(), AssetMedia.id.desc())
        )
    ).all()
    by_asset: dict[int, list[AssetMedia]] = {}
    for media in rows:
        if media.media_role == ASSET_MEDIA_ROLE_REFERENCE:
            continue
        by_asset.setdefault(int(media.asset_id), []).append(media)
    for asset_id, medias in by_asset.items():
        cover = next((m for m in medias if m.media_role == ASSET_MEDIA_ROLE_FINAL), medias[0])
        if cover.url and asset_id in id_to_public:
            result[id_to_public[asset_id]] = cover.url
    return result


# ---------------------------------------------------------------------------
# 异步任务：提交与子项
# ---------------------------------------------------------------------------

async def build_image_prompt_task_items(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    *,
    asset_public_id: str,
) -> list[TaskItemCreate]:
    """为单个资产构造生图专业提示词合成子项。"""

    project = await project_service.get_project_or_raise(session, project_public_id, user_public_id)
    text_model_id = str(project.text_model or "").strip()
    image_model_id = str(project.image_model or "").strip()
    if not text_model_id:
        raise asset_service.AssetServiceError("项目未绑定文本模型，请先在项目设置中选择文本模型")
    if not image_model_id:
        raise asset_service.AssetServiceError("项目未绑定图像模型，请先在项目设置中选择图像模型")
    normalized_asset_public_id = str(asset_public_id or "").strip()
    if not normalized_asset_public_id:
        raise asset_service.AssetServiceError("缺少资产 ID")
    asset = await asset_service.load_asset_or_raise(
        session,
        int(project.id),
        user_public_id,
        normalized_asset_public_id,
    )
    return [
        TaskItemCreate(
            item_type=ASSET_IMAGE_PROMPT_TASK_TYPE,
            item_key=f"asset-image-prompt:{normalized_asset_public_id}",
            payload={
                "project_public_id": project_public_id,
                "current_user_public_id": user_public_id,
                "model_id": text_model_id,
                "image_model_id": image_model_id,
                "asset_public_id": normalized_asset_public_id,
                "asset_name": asset.name,
            },
        )
    ]


async def submit_asset_image_prompt_task(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    *,
    asset_public_id: str,
    engine: Any | None = None,
) -> TaskJobDetail:
    """提交单个资产的生图专业提示词合成异步任务。"""

    items = await build_image_prompt_task_items(
        session,
        project_public_id,
        user_public_id,
        asset_public_id=asset_public_id,
    )
    item_payload = items[0].payload
    asset_name = str(item_payload.get("asset_name") or "").strip()
    resolved_engine = engine or asset_service.default_async_task_engine
    return await resolved_engine.create_and_enqueue_task_job(
        session,
        TaskJobCreate(
            task_type=ASSET_IMAGE_PROMPT_TASK_TYPE,
            queue_name=asset_service.ASSET_EXTRACT_QUEUE_NAME,
            name=f"资产生图提示词生成：{asset_name}" if asset_name else "资产生图提示词生成",
            created_by=user_public_id,
            payload={
                "project_public_id": project_public_id,
                "current_user_public_id": user_public_id,
                "model_id": str(item_payload.get("model_id") or ""),
                "asset_public_id": str(item_payload.get("asset_public_id") or ""),
            },
            items=items,
        ),
    )


async def build_image_generation_task_items(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    *,
    model_id: str,
    asset_public_ids: list[str],
    prompt: str = "",
    aspect_ratio: str = "",
    image_size: str = "",
    reference_media_public_ids: list[str] | None = None,
    count: int = 1,
) -> list[TaskItemCreate]:
    """按资产构造图像生成子项，逐个校验资产存在；count 张 → 每资产 count 个子项。"""

    project = await project_service.get_project_or_raise(session, project_public_id, user_public_id)
    resolved_model_id = str(project.image_model or "").strip()
    if not resolved_model_id:
        raise asset_service.AssetServiceError("项目未绑定图像模型，请先在项目设置中选择图像模型")
    normalized_count = max(1, min(4, int(count)))
    reference_media_ids = _dedupe_text_list(reference_media_public_ids)
    items: list[TaskItemCreate] = []
    for asset_public_id in asset_service._dedupe_public_ids(asset_public_ids):
        asset = await asset_service.load_asset_or_raise(session, int(project.id), user_public_id, asset_public_id)
        for index in range(normalized_count):
            items.append(
                TaskItemCreate(
                    item_type=ASSET_IMAGE_GENERATION_TASK_TYPE,
                    item_key=f"asset-image:{asset_public_id}:{index}",
                    payload={
                        "project_public_id": project_public_id,
                        "current_user_public_id": user_public_id,
                        "model_id": resolved_model_id,
                        "asset_public_id": asset_public_id,
                        "asset_name": asset.name,
                        "prompt": prompt,
                        "aspect_ratio": aspect_ratio,
                        "image_size": image_size,
                        "reference_media_public_ids": reference_media_ids,
                    },
                )
            )
    return items


async def submit_asset_image_generation_task(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    *,
    model_id: str,
    asset_public_ids: list[str],
    prompt: str = "",
    aspect_ratio: str = "",
    image_size: str = "",
    reference_media_public_ids: list[str] | None = None,
    count: int = 1,
    engine: Any | None = None,
) -> TaskJobDetail:
    """提交资产图像生成异步任务；一个 job 可含多个资产 × 多张子项。"""

    project = await project_service.get_project_or_raise(session, project_public_id, user_public_id)
    model_id = str(project.image_model or "").strip()
    if not model_id:
        raise asset_service.AssetServiceError("项目未绑定图像模型，请先在项目设置中选择图像模型")
    reference_media_ids = _dedupe_text_list(reference_media_public_ids)
    items = await build_image_generation_task_items(
        session,
        project_public_id,
        user_public_id,
        model_id=model_id,
        asset_public_ids=asset_public_ids,
        prompt=prompt,
        aspect_ratio=aspect_ratio,
        image_size=image_size,
        reference_media_public_ids=reference_media_ids,
        count=count,
    )
    if not items:
        raise asset_service.AssetServiceError("没有可用于图像生成的资产")

    job_name = "资产配图生成" if len(items) == 1 else f"资产批量配图：{len(items)} 张"
    resolved_engine = engine or asset_service.default_async_task_engine
    return await resolved_engine.create_and_enqueue_task_job(
        session,
        TaskJobCreate(
            task_type=ASSET_IMAGE_GENERATION_TASK_TYPE,
            queue_name=asset_service.ASSET_EXTRACT_QUEUE_NAME,
            name=job_name,
            created_by=user_public_id,
            payload={
                "project_public_id": project_public_id,
                "current_user_public_id": user_public_id,
                "model_id": model_id,
                "asset_count": len(items),
                "reference_media_count": len(reference_media_ids),
            },
            items=items,
        ),
    )