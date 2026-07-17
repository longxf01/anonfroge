from __future__ import annotations

"""剧本资产抽取服务。

从剧本管理中的分集正文抽取人物、势力、道具、场景资产，
并维护资产与分集的关联关系。
"""

import json
import re
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql import delete
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.tasks.engine import default_async_task_engine
from app.models.asset import (
    ASSET_RELATION_CHILD_OF,
    ASSET_STATUS_DRAFT,
    ASSET_STATUS_LOCKED,
    ASSET_TYPE_FACTION,
    ASSET_TYPE_LENS,
    ASSET_TYPE_PROP,
    ASSET_TYPE_ROLE,
    ASSET_TYPE_SCENE,
    Asset,
    AssetEpisode,
    AssetRelation,
)
from app.models.novel import NovelChapter
from app.models.script import ScriptEpisode, ScriptPlan
from app.schemas.tasks import TaskItemCreate, TaskJobCreate, TaskJobDetail
from app.services import project as project_service
from app.services import script as script_service
from app.services.agent_gateway import ProviderModelGateway, ProviderModelGatewayError
from app.services.prompt_registry import PromptRegistry
from app.services.screenwriting.rag_runtime import prepare_rag_context
from app.utils.time_tools import utc_now


ASSET_EXTRACT_TASK_TYPE = "asset.extract"
ASSET_EXTRACT_QUEUE_NAME = "asset"
EXTRACTABLE_ASSET_TYPES = {ASSET_TYPE_ROLE, ASSET_TYPE_FACTION, ASSET_TYPE_PROP, ASSET_TYPE_SCENE}
VALID_ASSET_TYPES = EXTRACTABLE_ASSET_TYPES | {ASSET_TYPE_LENS}


class AssetServiceError(Exception):
    """资产服务基础异常。"""

    def __init__(self, message: str, *, result: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.result = result or {}


class AssetNotFoundError(AssetServiceError):
    """资产不存在或无权访问。"""


def build_asset_gateway() -> ProviderModelGateway:
    """构建文本模型网关，便于测试替换。"""

    return ProviderModelGateway(timeout=settings.model_request_timeout_seconds)


async def _generate_full_text(gateway: Any, *, model_id: str, messages: list[dict[str, str]]) -> str:
    """以流式方式累计模型完整文本输出。"""

    parts: list[str] = []
    async for chunk in gateway.generate_stream(model_id=model_id, messages=messages):
        text = str(chunk or "")
        if text:
            parts.append(text)
    return "".join(parts).strip()


def parse_extracted_assets(raw: str) -> list[dict[str, Any]]:
    """解析模型返回的资产 JSON 数组。"""

    text = (raw or "").strip()
    if not text:
        return []
    fenced = re.search(r"```(?:json)?\s*(.+?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    else:
        start, end = text.find("["), text.rfind("]")
        if start != -1 and end != -1 and end > start:
            text = text[start : end + 1]

    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return []
    if not isinstance(data, list):
        return []

    normalized: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in data:
        if not isinstance(item, dict):
            continue
        asset_type = str(item.get("assetType") or "").strip().lower()
        name = str(item.get("name") or "").strip()
        if asset_type not in EXTRACTABLE_ASSET_TYPES or not name:
            continue
        key = (asset_type, name)
        if key in seen:
            continue
        seen.add(key)
        normalized.append(
            {
                "asset_type": asset_type,
                "name": name[:200],
                "keyword": str(item.get("keyword") or "").strip()[:500],
                "colors": str(item.get("colors") or "").strip()[:1000],
                "summary": str(item.get("summary") or "").strip(),
                "description": _coerce_mapping(item.get("description")),
                "details": _coerce_mapping(item.get("details")),
                "accessories": _coerce_mapping(item.get("accessories")),
                "episode_indices": set(),  # 分集归属由程序按当前抽取分集写入，不取模型返回
                "children": _normalize_asset_children(item.get("children")),
                "variant_label": "",
            }
        )
    return normalized


def _normalize_asset_children(value: Any) -> list[dict[str, Any]]:
    """标准化模型返回的 children 子资产数组。"""

    if not isinstance(value, list):
        return []
    children: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in value:
        if not isinstance(item, dict):
            continue
        asset_type = str(item.get("assetType") or "").strip().lower()
        name = str(item.get("name") or "").strip()
        if asset_type not in EXTRACTABLE_ASSET_TYPES or not name:
            continue
        key = (asset_type, name)
        if key in seen:
            continue
        seen.add(key)
        children.append(
            {
                "asset_type": asset_type,
                "name": name[:200],
                "keyword": str(item.get("keyword") or "").strip()[:500],
                "colors": str(item.get("colors") or "").strip()[:1000],
                "summary": str(item.get("summary") or "").strip(),
                "description": _coerce_mapping(item.get("description")),
                "details": _coerce_mapping(item.get("details")),
                "accessories": _coerce_mapping(item.get("accessories")),
                "episode_indices": set(),  # 分集归属由程序按当前抽取分集写入，不取模型返回
                "children": [],
                "variant_label": "",
            }
        )
    return children


def _coerce_mapping(value: Any) -> dict[str, Any]:
    """把对象字段标准化为字典。"""

    if isinstance(value, dict):
        return value
    return {}


def _dump_object_field(mapping: dict[str, Any]) -> str:
    """把对象字段序列化为数据库存储用 JSON 字符串。"""

    if not mapping:
        return "{}"
    return json.dumps(mapping, ensure_ascii=False)


def _render_object_text(mapping: dict[str, Any]) -> str:
    """把对象字段渲染为可读文本。"""

    parts: list[str] = []
    for key, value in mapping.items():
        text = str(value or "").strip()
        if text:
            parts.append(f"{key}：{text}")
    return "；".join(parts)


async def extract_assets(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    *,
    model_id: str,
    episode_public_ids: list[str] | None = None,
    gateway: Any | None = None,
) -> dict[str, Any]:
    """从剧本分集正文抽取资产并落库。"""

    model_id = model_id.strip()
    if not model_id:
        raise AssetServiceError("缺少抽取所用文本模型 ID")

    project = await project_service.get_project_or_raise(session, project_public_id, user_public_id)
    script_context, target_indices = await build_script_context(
        session,
        project_public_id,
        user_public_id,
        episode_public_ids,
    )
    messages = build_extraction_messages(script_context)
    prompt_trace = _model_prompt_trace(model_id=model_id, messages=messages)
    resolved_gateway = gateway or build_asset_gateway()
    try:
        raw = await _generate_full_text(resolved_gateway, model_id=model_id, messages=messages)
    except ProviderModelGatewayError as exc:
        raise AssetServiceError(f"资产抽取失败：{exc}") from exc
    prompt_trace["raw_output"] = raw
    prompt_trace["output_text"] = raw
    parsed = parse_extracted_assets(raw)
    if not parsed:
        raise AssetServiceError(
            "未能从剧本中抽取到有效资产，请检查剧本内容或模型输出",
            result=prompt_trace,
        )

    created = 0
    updated = 0
    results: list[Asset] = []
    enrichments: list[dict[str, Any]] = []
    target_set = set(target_indices)

    work_items: list[dict[str, Any]] = []
    for item in parsed:
        work_items.append({"item": item, "parent_item": None})
        for child in item.get("children") or []:
            work_items.append({"item": child, "parent_item": item})

    llm_enrichment_count = 0
    llm_enrichment_limit = max(0, int(settings.asset_enrichment_llm_limit))
    masters_by_item_id: dict[int, Asset] = {}
    for record in work_items:
        item = record["item"]
        enrichment = await enrich_asset_description(
            session,
            project,
            user_public_id,
            item,
            target_set,
            model_id=model_id,
            gateway=resolved_gateway,
            allow_llm_enrichment=llm_enrichment_count < llm_enrichment_limit,
        )
        if enrichment.get("llm_called"):
            llm_enrichment_count += 1
        enrichments.append(enrichment)

        master, master_new, derived, derived_new = await write_master_and_derivative(
            session,
            int(project.id),
            user_public_id,
            item,
            target_set,
            supplement=str(enrichment.get("supplement", "") or ""),
        )
        masters_by_item_id[id(item)] = master
        parent_item = record.get("parent_item")
        parent_asset = masters_by_item_id.get(id(parent_item)) if parent_item is not None else None
        if parent_asset is not None:
            await _upsert_child_relation(
                session,
                int(project.id),
                user_public_id,
                parent=parent_asset,
                child=master,
                label=str(master.variant_label or _infer_asset_state(item) or item.get("name") or "")[:120],
            )
        created += int(master_new) + int(derived_new)
        updated += int(not master_new) + int(not derived_new)
        results.append(master)
        results.append(derived)

    return {"created": created, "updated": updated, "assets": results, "asset_enrichment": enrichments, **prompt_trace}


async def submit_extract_assets_task(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    *,
    model_id: str,
    episode_public_ids: list[str] | None = None,
    engine: Any | None = None,
) -> TaskJobDetail:
    """提交剧本资产抽取异步任务。"""

    model_id = model_id.strip()
    if not model_id:
        raise AssetServiceError("缺少抽取所用文本模型 ID")

    await project_service.get_project_or_raise(session, project_public_id, user_public_id)
    items = await build_extract_task_items(
        session,
        project_public_id,
        user_public_id,
        model_id=model_id,
        episode_public_ids=episode_public_ids,
    )
    if not items:
        raise AssetServiceError("没有可用于资产抽取的分集")

    normalized_episode_ids = _dedupe_public_ids(episode_public_ids)
    resolved_engine = engine or default_async_task_engine
    return await resolved_engine.create_and_enqueue_task_job(
        session,
        TaskJobCreate(
            task_type=ASSET_EXTRACT_TASK_TYPE,
            queue_name=ASSET_EXTRACT_QUEUE_NAME,
            name="剧本资产抽取",
            created_by=user_public_id,
            payload={
                "project_public_id": project_public_id,
                "current_user_public_id": user_public_id,
                "model_id": model_id,
                "episode_public_ids": normalized_episode_ids,
            },
            items=items,
        ),
    )


async def build_extract_task_items(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    *,
    model_id: str,
    episode_public_ids: list[str] | None = None,
) -> list[TaskItemCreate]:
    """按抽取范围构造资产抽取任务子项。"""

    normalized_episode_ids = _dedupe_public_ids(episode_public_ids)
    if not normalized_episode_ids:
        plans = await script_service.list_plans(session, project_public_id, user_public_id)
        if not plans:
            return []
        plan = plans[0]
        _, episodes = await script_service.get_plan_detail(
            session,
            project_public_id,
            user_public_id,
            plan.public_id,
        )
        normalized_episode_ids = [
            str(episode.public_id).strip()
            for episode in episodes
            if str(episode.public_id).strip()
        ]
        if not normalized_episode_ids:
            return []

    items: list[TaskItemCreate] = []
    for episode_public_id in normalized_episode_ids:
        await script_service.get_episode_or_raise(
            session,
            project_public_id,
            user_public_id,
            episode_public_id,
        )
        items.append(
            TaskItemCreate(
                item_type=ASSET_EXTRACT_TASK_TYPE,
                item_key=f"episode:{episode_public_id}",
                payload={
                    "project_public_id": project_public_id,
                    "current_user_public_id": user_public_id,
                    "model_id": model_id,
                    "episode_public_ids": [episode_public_id],
                },
            )
        )
    return items


async def list_assets(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    *,
    asset_type: str = "",
) -> list[Asset]:
    """列出当前项目的资产，可按类型过滤。"""

    project = await project_service.get_project_or_raise(session, project_public_id, user_public_id)
    statement = select(Asset).where(
        Asset.project_id == project.id,
        Asset.user_public_id == user_public_id,
        Asset.disabled_at.is_(None),
    )
    normalized_type = asset_type.strip().lower()
    if normalized_type:
        if normalized_type not in VALID_ASSET_TYPES:
            raise AssetServiceError(f"不支持的资产类型：{asset_type}")
        statement = statement.where(Asset.asset_type == normalized_type)
    statement = statement.order_by(Asset.asset_type, Asset.name)
    return list((await session.exec(statement)).all())


async def get_asset(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    asset_public_id: str,
) -> Asset:
    """读取单个资产。"""

    project = await project_service.get_project_or_raise(session, project_public_id, user_public_id)
    return await load_asset_or_raise(session, project.id, user_public_id, asset_public_id)


async def get_asset_episode_items(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    asset: Asset,
) -> list[dict[str, str]]:
    """查询资产通过 AssetEpisode 关联的分集，返回展示用的分集 ID 与名称。"""

    project = await project_service.get_project_or_raise(session, project_public_id, user_public_id)
    if asset.id is None:
        return []
    statement = (
        select(ScriptEpisode, ScriptPlan)
        .join(AssetEpisode, AssetEpisode.episode_id == ScriptEpisode.id)
        .join(ScriptPlan, ScriptEpisode.plan_id == ScriptPlan.id)
        .where(
            ScriptPlan.project_id == project.id,
            ScriptPlan.user_public_id == user_public_id,
            ScriptPlan.disabled_at.is_(None),
            AssetEpisode.asset_id == int(asset.id),
            AssetEpisode.project_id == project.id,
            AssetEpisode.user_public_id == user_public_id,
            ScriptEpisode.disabled_at.is_(None),
        )
        .order_by(ScriptEpisode.episode_index, ScriptEpisode.id)
    )
    rows = list((await session.exec(statement)).all())
    return [
        {
            "episode_id": str(episode.public_id),
            "episode_name": f"第 {episode.episode_index} 集：{episode.title or '未命名分集'}",
        }
        for episode, _ in rows
    ]


async def set_asset_lock(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    asset_public_id: str,
    *,
    locked: bool,
) -> Asset:
    """锁定或解锁资产。"""

    asset = await get_asset(session, project_public_id, user_public_id, asset_public_id)
    asset.status = ASSET_STATUS_LOCKED if locked else ASSET_STATUS_DRAFT
    asset.updated_at = utc_now()
    session.add(asset)
    await session.flush()
    return asset


async def set_episode_assets(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    episode_public_id: str,
    asset_public_ids: list[str],
) -> dict[str, Any]:
    """覆盖设置指定分集关联的资产列表。"""

    episode, plan = await script_service.get_episode_or_raise(
        session,
        project_public_id,
        user_public_id,
        episode_public_id,
    )
    all_assets = await list_assets(session, project_public_id, user_public_id)
    assets_by_public_id = {asset.public_id: asset for asset in all_assets}
    selected_assets = [assets_by_public_id[public_id] for public_id in dict.fromkeys(asset_public_ids) if public_id in assets_by_public_id]
    selected_asset_ids = {int(asset.id) for asset in selected_assets if asset.id is not None}
    existing_links = list(
        (
            await session.exec(
                select(AssetEpisode).where(
                    AssetEpisode.project_id == int(plan.project_id),
                    AssetEpisode.user_public_id == user_public_id,
                    AssetEpisode.episode_id == int(episode.id),
                )
            )
        ).all()
    )
    existing_asset_ids = {int(link.asset_id) for link in existing_links}
    affected = 0
    for asset in all_assets:
        if asset.id is None:
            continue
        asset_id = int(asset.id)
        has_episode = asset_id in existing_asset_ids
        should_have = asset_id in selected_asset_ids
        if should_have and not has_episode:
            asset.updated_at = utc_now()
            session.add(asset)
            await _sync_asset_episode_links(session, int(plan.project_id), user_public_id, asset, {episode.episode_index})
            affected += 1
        elif has_episode and not should_have:
            asset.updated_at = utc_now()
            session.add(asset)
            await session.exec(
                delete(AssetEpisode).where(
                    AssetEpisode.asset_id == asset_id,
                    AssetEpisode.episode_id == int(episode.id),
                )
            )
            affected += 1
    await session.flush()
    return {"affected": affected, "assets": selected_assets}


async def build_script_context(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    episode_public_ids: list[str] | None = None,
) -> tuple[str, list[int]]:
    """构建给模型使用的剧本上下文。"""

    project = await project_service.get_project_or_raise(session, project_public_id, user_public_id)
    if episode_public_ids:
        episodes = []
        for episode_public_id in dict.fromkeys(episode_public_ids):
            episode, _ = await script_service.get_episode_or_raise(
                session,
                project_public_id,
                user_public_id,
                episode_public_id,
            )
            episodes.append(episode)
        episodes.sort(key=lambda item: item.episode_index)
        title = f"选定 {len(episodes)} 集"
    else:
        plans = await script_service.list_plans(session, project_public_id, user_public_id)
        if not plans:
            raise AssetServiceError("请先在剧本管理中同步或新建剧本，再抽取资产")
        plan = plans[0]
        _, episodes = await script_service.get_plan_detail(
            session,
            project_public_id,
            user_public_id,
            plan.public_id,
        )
        title = plan.title or "未命名剧本"

    if not episodes:
        raise AssetServiceError("当前剧本没有可用于资产抽取的分集内容")

    episode_indices = [episode.episode_index for episode in episodes]
    bound_chapters = await _load_bound_novel_chapters(session, project.id, episodes)
    lines = [f"剧名：{title}", ""]
    for episode in episodes:
        summary = (episode.summary or "").strip() or "（无梗概）"
        body = (episode.body or "").strip() or "（无正文）"
        lines.extend(
            [
                f"## 第 {episode.episode_index} 集：{episode.title or '未命名分集'}",
                f"梗概：{summary}",
                "正文：",
                body,
            ]
        )
        chapters = bound_chapters.get(episode.episode_index) or []
        if chapters:
            lines.append("绑定小说：")
            for chapter in chapters:
                lines.append(format_bound_novel_chapter(chapter))
        lines.append("")
    return "\n".join(lines).strip(), episode_indices


async def _load_bound_novel_chapters(
    session: AsyncSession,
    project_id: int,
    episodes: list[Any],
) -> dict[int, list[NovelChapter]]:
    """读取分集绑定的小说章节。"""

    chapter_indexes_by_episode: dict[int, list[int]] = {}
    unique_indexes: set[int] = set()
    for episode in episodes:
        indexes = parse_chapter_ids(getattr(episode, "novel_chapter_ids", ""))
        if not indexes:
            continue
        chapter_indexes_by_episode[episode.episode_index] = indexes
        unique_indexes.update(indexes)

    if not unique_indexes:
        return {}

    statement = (
        select(NovelChapter)
        .where(
            NovelChapter.project_id == project_id,
            NovelChapter.chapter_index.in_(unique_indexes),
            NovelChapter.disabled_at.is_(None),
        )
        .order_by(NovelChapter.chapter_index, NovelChapter.id)
    )
    rows = list((await session.exec(statement)).all())
    chapters_by_index: dict[int, list[NovelChapter]] = {}
    for chapter in rows:
        chapters_by_index.setdefault(chapter.chapter_index, []).append(chapter)

    result: dict[int, list[NovelChapter]] = {}
    for episode_index, indexes in chapter_indexes_by_episode.items():
        merged: list[NovelChapter] = []
        for index in indexes:
            merged.extend(chapters_by_index.get(index, []))
        if merged:
            result[episode_index] = merged
    return result


def parse_chapter_ids(value: str) -> list[int]:
    """解析逗号分隔的小说章节号。"""

    result: list[int] = []
    seen: set[int] = set()
    for item in (value or "").split(","):
        try:
            number = int(item.strip())
        except ValueError:
            continue
        if number <= 0 or number in seen:
            continue
        seen.add(number)
        result.append(number)
    return result


def format_bound_novel_chapter(chapter: NovelChapter) -> str:
    """格式化绑定小说章节。"""

    title = (chapter.title or "").strip() or f"第 {chapter.chapter_index} 章"
    content = (chapter.content or "").strip() or "（无正文）"
    return f"### 小说第 {chapter.chapter_index} 章：{title}\n{content}"


def build_extraction_messages(script_context: str) -> list[dict[str, str]]:
    """构建资产抽取提示词。"""

    system = load_asset_extraction_prompt()
    user = f"## 剧本上下文\n{script_context}\n\n请抽取可用于制作的资产清单。"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


async def enrich_asset_description(
    session: AsyncSession,
    project: Any,
    user_public_id: str,
    item: dict[str, Any],
    episode_indices: set[int],
    *,
    model_id: str,
    gateway: Any,
    allow_llm_enrichment: bool = True,
) -> dict[str, Any]:
    """用项目 RAG 检索正文细节补全资产描述。"""

    description_text = _render_object_text(_coerce_mapping(item.get("description")))
    asset_type = str(item.get("asset_type") or "").strip()
    name = str(item.get("name") or "").strip()
    if not name:
        return {"name": name, "asset_type": asset_type, "supplement": "", "status": "skipped"}

    query = build_asset_rag_query(item, episode_indices)
    try:
        rag_preparation = await prepare_rag_context(
            session,
            project,
            project.public_id,
            user_public_id,
            query,
        )
    except Exception as exc:
        return {
            "name": name,
            "asset_type": asset_type,
            "supplement": "",
            "status": "rag_failed",
            "error": str(exc),
        }

    rag_context = rag_preparation.context
    rag_text = str(getattr(rag_context, "text", "") or "").strip()
    rag_runtime = dict(getattr(rag_context, "runtime", {}) or {})
    if not rag_text:
        return {
            "name": name,
            "asset_type": asset_type,
            "supplement": "",
            "status": "no_rag_context",
            "rag_runtime": rag_runtime,
        }

    if not allow_llm_enrichment:
        return {
            "name": name,
            "asset_type": asset_type,
            "supplement": "",
            "status": "skipped_enrichment_limit",
            "rag_runtime": rag_runtime,
        }

    messages = build_asset_enrichment_messages(
        asset_type=asset_type,
        name=name,
        description=description_text,
        episode_indices=episode_indices,
        rag_context=rag_text,
    )
    try:
        enhanced = await _generate_full_text(gateway, model_id=model_id, messages=messages)
    except Exception as exc:
        return {
            "name": name,
            "asset_type": asset_type,
            "supplement": "",
            "status": "llm_failed",
            "error": str(exc),
            "rag_runtime": rag_runtime,
            "llm_called": True,
        }

    return {
        "name": name,
        "asset_type": asset_type,
        "supplement": enhanced,
        "status": "enriched" if enhanced else "empty_enrichment",
        "rag_runtime": rag_runtime,
        "llm_called": True,
    }


def build_asset_rag_query(item: dict[str, Any], episode_indices: set[int]) -> str:
    """为资产详情补全构造 RAG 查询文本。"""

    name = str(item.get("name") or "").strip()
    asset_type = str(item.get("asset_type") or "").strip()
    description = _render_object_text(_coerce_mapping(item.get("description")))
    episodes = "、".join(str(index) for index in sorted(episode_indices)) or "未知"
    return (
        f"资产名称：{name}\n"
        f"资产类型：{asset_type}\n"
        f"关联集数：{episodes}\n"
        f"当前描述：{description}\n"
        "请检索小说正文中与该资产相关的外观、尺寸、位置、关系、用途、势力或衍生场景细节。"
    )


def build_asset_enrichment_messages(
    *,
    asset_type: str,
    name: str,
    description: str,
    episode_indices: set[int],
    rag_context: str,
) -> list[dict[str, str]]:
    """构建资产细节补全提示词。"""

    system = (
        "你是短剧制作资产设定整理助手，只根据提供的 RAG 检索片段补全单个资产的制作细节。"
        "只输出补全后的细节文本，不要输出 JSON、Markdown 或解释。"
        "不得编造检索片段中没有的信息；缺失信息保留原描述或写“未知”。"
        "使用短句和分号分隔，保留资产类型要求中的关键描述维度。"
    )
    episodes = "、".join(str(index) for index in sorted(episode_indices)) or "未知"
    user = (
        f"资产类型：{asset_type}\n"
        f"资产名称：{name}\n"
        f"关联集数：{episodes}\n"
        f"原描述：{description}\n\n"
        "RAG 检索片段：\n"
        f"{rag_context}\n\n"
        "请输出补全后的细节文本。"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


async def write_master_and_derivative(
    session: AsyncSession,
    project_id: int,
    user_public_id: str,
    item: dict[str, Any],
    incoming_indices: set[int],
    *,
    supplement: str,
) -> tuple[Asset, bool, Asset, bool]:
    """写入资产的主记录与衍生记录。

    首次出现：建主资产（parent 为空）+ 衍生资产（parent 指向主资产，name 为“主名·状态名”）。
    再次出现：主资产累加剧集；按状态名命中已有衍生则合并剧集，否则新增一条衍生。
    返回（主资产, 主是否新建, 衍生资产, 衍生是否新建）。
    """

    asset_type = str(item["asset_type"])
    master_name = str(item["name"]).strip()
    state = _infer_asset_state(item)
    derived_name = _derive_variant_asset_name(master_name, state)
    enriched = _with_supplement(item, supplement)

    master_item = {**enriched, "name": master_name, "main_asset": True, "variant_label": ""}
    master, master_new = await _upsert_asset(
        session,
        project_id,
        user_public_id,
        (asset_type, master_name),
        item=master_item,
        incoming_indices=incoming_indices,
    )

    derived_item = {**enriched, "name": derived_name, "main_asset": False, "variant_label": state}
    derived, derived_new = await _upsert_asset(
        session,
        project_id,
        user_public_id,
        (asset_type, derived_name),
        item=derived_item,
        incoming_indices=incoming_indices,
    )
    await _upsert_child_relation(
        session,
        project_id,
        user_public_id,
        parent=master,
        child=derived,
        label=state,
    )
    return master, master_new, derived, derived_new


async def _upsert_child_relation(
    session: AsyncSession,
    project_id: int,
    user_public_id: str,
    *,
    parent: Asset,
    child: Asset,
    label: str,
) -> None:
    """写入或更新子资产指向父资产的 child_of 关系，已存在则保持幂等。"""

    if parent.id is None or child.id is None:
        return
    statement = select(AssetRelation).where(
        AssetRelation.source_asset_id == int(child.id),
        AssetRelation.target_asset_id == int(parent.id),
        AssetRelation.relation_type == ASSET_RELATION_CHILD_OF,
    )
    relation = (await session.exec(statement)).first()
    relation_label = str(label or child.variant_label or "").strip()[:120]
    if relation is not None:
        if relation_label and relation.relation_label != relation_label:
            relation.relation_label = relation_label
            session.add(relation)
            await session.flush()
        return

    relation = AssetRelation(
        source_asset_id=int(child.id),
        target_asset_id=int(parent.id),
        relation_type=ASSET_RELATION_CHILD_OF,
        relation_label=relation_label,
    )
    session.add(relation)
    await session.flush()


async def _upsert_asset(
    session: AsyncSession,
    project_id: int,
    user_public_id: str,
    key: tuple[str, str],
    *,
    item: dict[str, Any],
    incoming_indices: set[int],
) -> tuple[Asset, bool]:
    """按 (asset_type, name) 唯一键写入资产：已存在则累加剧集，不存在则新建。返回（资产, 是否新建）。"""

    await _lock_asset_key(session, project_id, user_public_id, key)
    asset = await load_existing_asset_by_key(session, project_id, user_public_id, key)
    if asset is not None:
        await _accumulate_episodes(session, asset, item, incoming_indices)
        await _sync_asset_episode_links(session, project_id, user_public_id, asset, incoming_indices)
        return asset, False

    asset_type, name = key
    asset = Asset(
        project_id=project_id,
        user_public_id=user_public_id,
        asset_type=asset_type,
        name=name,
        main_asset=bool(item.get("main_asset")),
        variant_label=str(item.get("variant_label") or "")[:100],
    )
    apply_asset_record(asset, item, incoming_indices)
    try:
        async with session.begin_nested():
            session.add(asset)
            await session.flush()
    except IntegrityError:
        existing = await load_existing_asset_by_key(session, project_id, user_public_id, key)
        if existing is None:
            raise
        await _accumulate_episodes(session, existing, item, incoming_indices)
        await _sync_asset_episode_links(session, project_id, user_public_id, existing, incoming_indices)
        return existing, False
    await _sync_asset_episode_links(session, project_id, user_public_id, asset, incoming_indices)
    return asset, True


async def _lock_asset_key(
    session: AsyncSession,
    project_id: int,
    user_public_id: str,
    key: tuple[str, str],
) -> None:
    """PostgreSQL 下按资产唯一键加事务级锁，避免并发插入同名资产死锁。"""

    bind = session.get_bind()
    dialect_name = getattr(getattr(bind, "dialect", None), "name", "")
    if dialect_name != "postgresql":
        return
    asset_type, name = key
    lock_key = f"asset:{project_id}:{user_public_id}:{asset_type}:{name}"
    await session.exec(
        text("select pg_advisory_xact_lock(hashtextextended(:lock_key, 0))").bindparams(lock_key=lock_key)
    )


async def _accumulate_episodes(
    session: AsyncSession,
    asset: Asset,
    item: dict[str, Any],
    incoming_indices: set[int],
) -> None:
    """已存在资产：累加剧集并确保 parent 指向主资产，不覆盖其它字段；锁定资产跳过。"""

    if asset.status == ASSET_STATUS_LOCKED:
        return
    merge_asset_missing_fields(asset, item)
    if "main_asset" in item:
        asset.main_asset = bool(item.get("main_asset"))
    if not str(asset.variant_label or "").strip():
        asset.variant_label = str(item.get("variant_label") or "")[:100]
    asset.updated_at = utc_now()
    session.add(asset)
    await session.flush()


async def _sync_asset_episode_links(
    session: AsyncSession,
    project_id: int,
    user_public_id: str,
    asset: Asset,
    episode_indices: set[int],
) -> None:
    """同步资产与分集的关联记录，按集号补充缺失关联，已存在则跳过。"""

    if asset.id is None or not episode_indices:
        return
    statement = (
        select(ScriptEpisode)
        .join(ScriptPlan, ScriptEpisode.plan_id == ScriptPlan.id)
        .where(
            ScriptPlan.project_id == project_id,
            ScriptPlan.user_public_id == user_public_id,
            ScriptPlan.disabled_at.is_(None),
            ScriptEpisode.episode_index.in_(episode_indices),
            ScriptEpisode.disabled_at.is_(None),
        )
    )
    episodes = list((await session.exec(statement)).all())
    for episode in episodes:
        existing_statement = select(AssetEpisode).where(
            AssetEpisode.asset_id == int(asset.id),
            AssetEpisode.episode_id == int(episode.id),
        )
        if (await session.exec(existing_statement)).first() is not None:
            continue
        session.add(
            AssetEpisode(
                project_id=project_id,
                user_public_id=user_public_id,
                asset_id=int(asset.id),
                episode_id=int(episode.id),
                episode_index=int(episode.episode_index),
            )
        )
    await session.flush()


def _infer_asset_state(item: dict[str, Any]) -> str:
    """从 description 推断资产的状态/形态名；无明确状态返回空串。"""

    description = _coerce_mapping(item.get("description"))
    for key in ("状态", "形态", "阶段", "年龄阶段", "变体标签", "状态标签"):
        text = str(description.get(key) or "").strip()
        if text:
            return _normalize_variant_label(text)
    scene_type = str(description.get("场景类型") or "").strip()
    if "衍生" in scene_type:
        return "衍生资产"
    return ""


def _normalize_variant_label(value: str) -> str:
    """把状态描述压缩为短标签，避免长文进入 variant_label。"""

    text = re.split(r"[，,；;。.\n\r]", str(value or "").strip(), maxsplit=1)[0].strip()
    if len(text) <= 20:
        return text[:100]
    return text[:20]


def _derive_variant_asset_name(master_name: str, state: str) -> str:
    """构造衍生资产名：主名·状态名；无状态名时用固定后缀，避免与主资产撞名。"""

    master_name = (master_name or "").strip()
    state = (state or "").strip()
    suffix = state if state and state != master_name else "衍生"
    return f"{master_name}·{suffix}"[:200]


def _with_supplement(item: dict[str, Any], supplement: str) -> dict[str, Any]:
    """把 RAG 补全文本并入 description 的“细节补全”键。"""

    result = dict(item)
    description = dict(_coerce_mapping(item.get("description")))
    supplement_text = str(supplement or "").strip()
    if supplement_text:
        description["细节补全"] = supplement_text
    result["description"] = description
    return result



def merge_asset_missing_fields(asset: Asset, item: dict[str, Any]) -> None:
    """把抽取项字段合并进已有资产，仅补充缺失字段，不覆盖已有内容。"""

    asset.keyword = _prefer_existing_text(asset.keyword, item.get("keyword"))
    asset.colors = _prefer_existing_text(asset.colors, item.get("colors"))
    asset.summary = _prefer_existing_text(asset.summary, item.get("summary"))
    asset.description = _dump_object_field(
        _merge_object_field(_parse_object_field(asset.description), _coerce_mapping(item.get("description")))
    )
    asset.details = _dump_object_field(
        _merge_object_field(_parse_object_field(asset.details), _coerce_mapping(item.get("details")))
    )
    asset.accessories = _dump_object_field(
        _merge_object_field(_parse_object_field(asset.accessories), _coerce_mapping(item.get("accessories")))
    )


def _prefer_existing_text(existing: Any, incoming: Any) -> str:
    existing_text = str(existing or "").strip()
    if existing_text:
        return str(existing or "")
    return str(incoming or "")


def _parse_object_field(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    text = str(value or "").strip()
    if not text:
        return {}
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _merge_object_field(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing)
    for key, value in incoming.items():
        normalized_key = str(key or "").strip()
        if not normalized_key:
            continue
        existing_value = merged.get(normalized_key)
        if isinstance(existing_value, dict) and isinstance(value, dict):
            nested = _merge_object_field(existing_value, value)
            if nested:
                merged[normalized_key] = nested
            continue
        if str(existing_value or "").strip():
            continue
        if isinstance(value, dict):
            if value:
                merged[normalized_key] = value
            continue
        if str(value or "").strip():
            merged[normalized_key] = value
    return merged

def apply_asset_record(asset: Asset, item: dict[str, Any], incoming_indices: set[int]) -> None:
    """把抽取项的字段写入资产记录。"""

    asset.keyword = str(item.get("keyword") or "")
    asset.colors = str(item.get("colors") or "")
    asset.summary = str(item.get("summary") or "")
    asset.description = _dump_object_field(_coerce_mapping(item.get("description")))
    asset.details = _dump_object_field(_coerce_mapping(item.get("details")))
    asset.accessories = _dump_object_field(_coerce_mapping(item.get("accessories")))
    asset.main_asset = bool(item.get("main_asset"))
    asset.variant_label = str(item.get("variant_label") or "")[:100]
    asset.updated_at = utc_now()


def load_asset_extraction_prompt(registry: PromptRegistry | None = None) -> str:
    """从 data/skills 读取资产抽取核心提示词。"""

    prompt_name = settings.asset_extraction_prompt_name.strip()
    if not prompt_name:
        raise AssetServiceError("资产抽取提示词名称未配置")
    prompt_registry = registry or PromptRegistry.from_settings()
    return prompt_registry.skill(prompt_name)


def _model_prompt_trace(*, model_id: str, messages: list[dict[str, str]]) -> dict[str, Any]:
    """记录资产抽取模型调用的提示词信息。"""

    return {
        "model_id": model_id,
        "messages": messages,
        "composed_prompt": _format_model_messages(messages),
    }


def _format_model_messages(messages: list[dict[str, str]]) -> str:
    parts: list[str] = []
    for index, message in enumerate(messages, start=1):
        role = str(message.get("role") or f"message_{index}").strip()
        content = str(message.get("content") or "").strip()
        if content:
            parts.append(f"{role}：\n{content}")
    return "\n\n".join(parts)


def parse_episode_indices(value: str) -> set[int]:
    """解析数据库中的逗号分隔集号。"""

    indices: set[int] = set()
    for item in (value or "").split(","):
        try:
            number = int(item.strip())
        except ValueError:
            continue
        if number > 0:
            indices.add(number)
    return indices


def join_episode_indices(indices: set[int]) -> str:
    """把集号集合格式化为升序逗号分隔字符串。"""

    return ",".join(str(number) for number in sorted(indices))


def _dedupe_public_ids(values: list[str] | None) -> list[str]:
    """去重并清洗 public_id 列表。"""

    if not values:
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


async def get_or_create_asset(
    session: AsyncSession,
    project: Any,
    user_public_id: str,
    asset_type: str,
    name: str,
) -> tuple[Asset, bool]:
    """按唯一键获取或创建资产。"""

    statement = select(Asset).where(
        Asset.project_id == project.id,
        Asset.user_public_id == user_public_id,
        Asset.asset_type == asset_type,
        Asset.name == name,
        Asset.disabled_at.is_(None),
    )
    asset = (await session.exec(statement)).first()
    if asset is not None:
        return asset, False

    asset = Asset(
        project_id=project.id,
        user_public_id=user_public_id,
        asset_type=asset_type,
        name=name,
    )
    session.add(asset)
    await session.flush()
    return asset, True


async def load_existing_asset_by_key(
    session: AsyncSession,
    project_id: int,
    user_public_id: str,
    key: tuple[str, str],
) -> Asset | None:
    """按资产唯一键读取单个未禁用资产。"""

    asset_type, name = key
    statement = select(Asset).where(
        Asset.project_id == project_id,
        Asset.user_public_id == user_public_id,
        Asset.asset_type == asset_type,
        Asset.name == name,
        Asset.disabled_at.is_(None),
    )
    return (await session.exec(statement)).first()


async def load_asset_or_raise(
    session: AsyncSession,
    project_id: int,
    user_public_id: str,
    asset_public_id: str,
) -> Asset:
    """读取单个资产，不存在则抛出业务异常。"""

    statement = select(Asset).where(
        Asset.project_id == project_id,
        Asset.user_public_id == user_public_id,
        Asset.public_id == asset_public_id,
        Asset.disabled_at.is_(None),
    )
    asset = (await session.exec(statement)).first()
    if asset is None:
        raise AssetNotFoundError("资产不存在或无权访问")
    return asset
