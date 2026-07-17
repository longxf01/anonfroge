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
from typing import Any

import httpx
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import BASE_DIR, settings
from app.models.asset import (
    ASSET_GENERATION_STATUS_FAILED,
    ASSET_GENERATION_STATUS_RUNNING,
    ASSET_GENERATION_STATUS_SUCCEEDED,
    ASSET_GENERATION_TYPE_IMAGE,
    ASSET_MEDIA_ROLE_FINAL,
    ASSET_MEDIA_ROLE_GENERATED,
    ASSET_MEDIA_TYPE_IMAGE,
    Asset,
    AssetGeneration,
    AssetMedia,
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


ASSET_IMAGE_GENERATION_TASK_TYPE = "asset.image_generation"

_MIME_EXT = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/webp": "webp",
    "image/gif": "gif",
}

_STYLE_PATH_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,119}$")


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

    project = await project_service.get_project_or_raise(session, project_public_id, user_public_id)
    text_model_id = str(project.text_model or "").strip()
    image_model_id = str(project.image_model or "").strip()
    if not text_model_id:
        raise asset_service.AssetServiceError("项目未绑定文本模型，请先在项目设置中选择文本模型")
    if not image_model_id:
        raise asset_service.AssetServiceError("项目未绑定图像模型，请先在项目设置中选择图像模型")
    asset = await asset_service.load_asset_or_raise(session, int(project.id), user_public_id, asset_public_id)
    messages = build_asset_image_prompt_messages(
        asset=asset,
        image_model_id=image_model_id,
        art_style_id=str(project.art_style or "").strip(),
        art_style_text=_resolve_art_style_text(project),
    )
    resolved_gateway = gateway or asset_service.build_asset_gateway()
    try:
        output = await asset_service._generate_full_text(resolved_gateway, model_id=text_model_id, messages=messages)
    except ProviderModelGatewayError as exc:
        raise asset_service.AssetServiceError(f"资产生图提示词合成失败：{exc}") from exc
    prompt = _strip_prompt_fence(output)
    if not prompt:
        raise asset_service.AssetServiceError("资产生图提示词合成结果为空")
    return prompt


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
    make_cover: bool = True,
    gateway: Any | None = None,
) -> dict[str, Any]:
    """为单个资产生成图像：写生成记录 → 调网关 → 落盘 → 写媒体 → 设封面。"""

    project = await project_service.get_project_or_raise(session, project_public_id, user_public_id)
    model_id = str(project.image_model or "").strip()
    if not model_id:
        raise asset_service.AssetServiceError("项目未绑定图像模型，请先在项目设置中选择图像模型")
    asset = await asset_service.load_asset_or_raise(session, int(project.id), user_public_id, asset_public_id)

    resolved_gateway = gateway or build_media_gateway()
    final_prompt = (prompt or "").strip()
    if not final_prompt:
        final_prompt = await synthesize_asset_image_prompt(
            session,
            project_public_id,
            user_public_id,
            asset_public_id=asset_public_id,
            gateway=resolved_gateway if gateway is not None else None,
        )
    if not final_prompt:
        raise asset_service.AssetServiceError("资产信息不足以生成图像提示词")

    generation = AssetGeneration(
        project_id=int(project.id),
        user_public_id=user_public_id,
        asset_id=int(asset.id),
        generation_type=ASSET_GENERATION_TYPE_IMAGE,
        model_id=model_id,
        prompt=final_prompt,
        parameters=json.dumps(
            {"aspect_ratio": aspect_ratio.strip(), "image_size": image_size.strip()}, ensure_ascii=False
        ),
        status=ASSET_GENERATION_STATUS_RUNNING,
        started_at=utc_now(),
    )
    session.add(generation)
    await session.flush()

    gen_kwargs: dict[str, Any] = {}
    if aspect_ratio.strip():
        gen_kwargs["aspect_ratio"] = aspect_ratio.strip()
    if image_size.strip():
        gen_kwargs["image_size"] = image_size.strip()
    try:
        output = await resolved_gateway.generate_image(model_id=model_id, prompt=final_prompt, **gen_kwargs)
        data = await _resolve_media_bytes(output)
    except (ProviderModelGatewayError, asset_service.AssetServiceError) as exc:
        generation.status = ASSET_GENERATION_STATUS_FAILED
        generation.error_message = str(exc)
        generation.completed_at = utc_now()
        session.add(generation)
        await session.flush()
        raise asset_service.AssetServiceError(
            f"图像生成失败：{exc}",
            result={"asset_public_id": asset_public_id, "generation_public_id": generation.public_id},
        ) from exc

    media = AssetMedia(
        project_id=int(project.id),
        user_public_id=user_public_id,
        asset_id=int(asset.id),
        media_type=ASSET_MEDIA_TYPE_IMAGE,
        media_role=ASSET_MEDIA_ROLE_GENERATED,
        mime_type=output.mime_type or "image/png",
        width=output.width,
        height=output.height,
        prompt=final_prompt,
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

    generation.status = ASSET_GENERATION_STATUS_SUCCEEDED
    generation.completed_at = utc_now()
    generation.output = json.dumps({"media_public_id": media.public_id, "url": media.url}, ensure_ascii=False)
    session.add(generation)
    await session.flush()

    if make_cover:
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

    return {"media": media, "generation": generation}


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
                AssetMedia.user_public_id == user_public_id,
                AssetMedia.disabled_at.is_(None),
            )
            .order_by(AssetMedia.created_at.desc(), AssetMedia.id.desc())
        )
    ).all()
    by_asset: dict[int, list[AssetMedia]] = {}
    for media in rows:
        by_asset.setdefault(int(media.asset_id), []).append(media)
    for asset_id, medias in by_asset.items():
        cover = next((m for m in medias if m.media_role == ASSET_MEDIA_ROLE_FINAL), medias[0])
        if cover.url and asset_id in id_to_public:
            result[id_to_public[asset_id]] = cover.url
    return result


# ---------------------------------------------------------------------------
# 异步任务：提交与子项
# ---------------------------------------------------------------------------

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
    count: int = 1,
) -> list[TaskItemCreate]:
    """按资产构造图像生成子项，逐个校验资产存在；count 张 → 每资产 count 个子项。"""

    project = await project_service.get_project_or_raise(session, project_public_id, user_public_id)
    resolved_model_id = str(project.image_model or "").strip()
    if not resolved_model_id:
        raise asset_service.AssetServiceError("项目未绑定图像模型，请先在项目设置中选择图像模型")
    normalized_count = max(1, min(4, int(count)))
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
    count: int = 1,
    engine: Any | None = None,
) -> TaskJobDetail:
    """提交资产图像生成异步任务；一个 job 可含多个资产 × 多张子项。"""

    project = await project_service.get_project_or_raise(session, project_public_id, user_public_id)
    model_id = str(project.image_model or "").strip()
    if not model_id:
        raise asset_service.AssetServiceError("项目未绑定图像模型，请先在项目设置中选择图像模型")
    items = await build_image_generation_task_items(
        session,
        project_public_id,
        user_public_id,
        model_id=model_id,
        asset_public_ids=asset_public_ids,
        prompt=prompt,
        aspect_ratio=aspect_ratio,
        image_size=image_size,
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
            },
            items=items,
        ),
    )
