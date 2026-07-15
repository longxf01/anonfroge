"""剧本创作 RAG 索引与语义检索上下文编排。"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from app.core.config import Settings, settings
from app.core.rag.constants import DEFAULT_SCREENWRITING_RAG_INDEX_CHUNK_BATCH_SIZE
from app.core.harness.memory.vector import RetrievedChunk, VectorMemory, lexical_score
from app.core.rag import RagDocument


LEXICAL_CONTEXT_CHARS = 1200
CHUNK_CONTENT_HASH_METADATA_KEY = "chunk_content_hash"


class _RuntimeVectorMemory(VectorMemory, Protocol):
    vector_ready: bool

    def runtime_metadata(self) -> dict[str, Any]:
        """返回向量记忆运行状态。"""


@dataclass(frozen=True)
class ScreenwritingRagHit:
    """一次 RAG 召回命中。"""

    document: RagDocument
    score: float
    chunk_text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ScreenwritingRagContext:
    """可注入提示词的 RAG 上下文。"""

    hits: list[ScreenwritingRagHit]
    text: str
    runtime: dict[str, Any]


class ScreenwritingRagIndex:
    """基于通用向量记忆的剧本创作 RAG 语义索引。"""

    def __init__(
        self,
        *,
        vector_memory: _RuntimeVectorMemory | None = None,
        chunk_chars: int | None = None,
        chunk_overlap: int | None = None,
        chunk_batch_size: int | None = None,
        min_vector_score: float | None = None,
        vector_store_dir: str | Path | None = None,
        config: Settings | None = None,
    ) -> None:
        if vector_memory is None:
            from app.core.harness.memory.vector import ChromaVectorMemory

            vector_memory = ChromaVectorMemory(vector_store_dir=vector_store_dir)
        current_config = config or settings
        self.vector_memory = vector_memory
        self.chunk_chars = max(1, int(chunk_chars if chunk_chars is not None else current_config.screenwriting_rag_chunk_chars))
        self.chunk_overlap = max(0, int(chunk_overlap if chunk_overlap is not None else current_config.screenwriting_rag_chunk_overlap))
        configured_chunk_batch_size = getattr(
            current_config,
            "screenwriting_rag_index_chunk_batch_size",
            DEFAULT_SCREENWRITING_RAG_INDEX_CHUNK_BATCH_SIZE,
        )
        self.chunk_batch_size = max(
            1,
            int(chunk_batch_size if chunk_batch_size is not None else configured_chunk_batch_size),
        )
        self.min_vector_score = float(min_vector_score if min_vector_score is not None else current_config.screenwriting_rag_min_vector_score)

    @property
    def vector_ready(self) -> bool:
        """返回向量检索是否可用。"""
        return bool(getattr(self.vector_memory, "vector_ready", False))

    def index_documents(self, isolation_key: str, documents: Sequence[RagDocument]) -> None:
        """把 RAG 文档切分后写入向量记忆。"""
        self.clear_scope(isolation_key)
        self.upsert_documents(isolation_key, documents)

    def clear_scope(self, isolation_key: str) -> None:
        """清空同一隔离范围内的旧向量文档。"""
        replace_scope = getattr(self.vector_memory, "replace_scope", None)
        if callable(replace_scope):
            replace_scope(isolation_key, [])

    def upsert_documents(
        self,
        isolation_key: str,
        documents: Sequence[RagDocument],
        *,
        skip_unchanged: bool = False,
        indexed_ids: set[str] | None = None,
    ) -> int:
        """把一批 RAG 文档切分后分批写入向量记忆，返回实际写入的 chunk 数。"""
        chunk_count = 0
        for chunk_documents, chunk_metadata, chunk_ids in _iter_chunk_payload_batches(
            documents,
            isolation_key=isolation_key,
            chunk_chars=self.chunk_chars,
            chunk_overlap=self.chunk_overlap,
            chunk_batch_size=self.chunk_batch_size,
        ):
            if indexed_ids is not None:
                indexed_ids.update(chunk_ids)
            if skip_unchanged:
                chunk_documents, chunk_metadata, chunk_ids = self._changed_chunk_payload(
                    chunk_documents,
                    chunk_metadata,
                    chunk_ids,
                )
                if not chunk_documents:
                    continue
            self.vector_memory.upsert(
                isolation_key,
                chunk_documents,
                metadata=chunk_metadata,
                ids=chunk_ids,
            )
            chunk_count += len(chunk_documents)
        return chunk_count

    @property
    def incremental_refresh_ready(self) -> bool:
        """返回向量记忆是否支持按 id 比对和删除旧 chunk。"""
        return all(
            callable(getattr(self.vector_memory, method_name, None))
            for method_name in ("existing_metadata_by_id", "scope_ids", "delete_ids")
        )

    def delete_stale_documents(self, isolation_key: str, indexed_ids: set[str]) -> int:
        """删除当前刷新过程中没有出现的旧 chunk。"""
        scope_ids = getattr(self.vector_memory, "scope_ids", None)
        delete_ids = getattr(self.vector_memory, "delete_ids", None)
        if not callable(scope_ids) or not callable(delete_ids):
            return 0
        stale_ids = [id_value for id_value in scope_ids(isolation_key) if id_value not in indexed_ids]
        if not stale_ids:
            return 0
        delete_ids(stale_ids)
        return len(stale_ids)

    def _changed_chunk_payload(
        self,
        chunk_documents: list[str],
        chunk_metadata: list[dict[str, Any]],
        chunk_ids: list[str],
    ) -> tuple[list[str], list[dict[str, Any]], list[str]]:
        existing_metadata_by_id = getattr(self.vector_memory, "existing_metadata_by_id", None)
        if not callable(existing_metadata_by_id):
            return chunk_documents, chunk_metadata, chunk_ids
        existing_metadata = existing_metadata_by_id(chunk_ids)
        if not existing_metadata:
            return chunk_documents, chunk_metadata, chunk_ids

        changed_documents: list[str] = []
        changed_metadata: list[dict[str, Any]] = []
        changed_ids: list[str] = []
        for document, metadata, id_value in zip(chunk_documents, chunk_metadata, chunk_ids, strict=True):
            existing = existing_metadata.get(id_value) or {}
            if existing.get(CHUNK_CONTENT_HASH_METADATA_KEY) == metadata.get(CHUNK_CONTENT_HASH_METADATA_KEY):
                continue
            changed_documents.append(document)
            changed_metadata.append(metadata)
            changed_ids.append(id_value)
        return changed_documents, changed_metadata, changed_ids

    def retrieve_context(
        self,
        isolation_key: str,
        query: str,
        documents: Sequence[RagDocument],
        *,
        limit: int = 50,
    ) -> ScreenwritingRagContext:
        """检索并编排可注入提示词的 RAG 上下文。"""
        safe_limit = max(1, int(limit))
        query_text = query.strip()
        vector_runtime = self._runtime_metadata()
        vector_hits, vector_failure_reason = self._vector_hits(
            isolation_key,
            query_text,
            documents,
            safe_limit,
        )
        if vector_hits:
            runtime = {
                **_runtime_with_failure(vector_runtime, vector_failure_reason),
                "retrievalMode": "vector",
                "retrievalStrategy": "semantic",
                "hitCount": len(vector_hits),
                "minVectorScore": self.min_vector_score,
            }
            return ScreenwritingRagContext(
                hits=vector_hits,
                text=_format_context_text(vector_hits),
                runtime=runtime,
            )

        lexical_hits = _lexical_fallback_hits(query_text, documents, limit=safe_limit)
        if lexical_hits:
            runtime = {
                **_runtime_with_failure(vector_runtime, vector_failure_reason),
                "retrievalMode": "lexical_fallback",
                "retrievalStrategy": "lexical_score",
                "hitCount": len(lexical_hits),
                "minVectorScore": self.min_vector_score,
            }
            return ScreenwritingRagContext(
                hits=lexical_hits,
                text=_format_context_text(lexical_hits),
                runtime=runtime,
            )

        runtime = {
            **_runtime_with_failure(vector_runtime, vector_failure_reason),
            "retrievalMode": "empty",
            "retrievalStrategy": "none",
            "hitCount": 0,
            "minVectorScore": self.min_vector_score,
        }
        return ScreenwritingRagContext(hits=[], text="", runtime=runtime)

    def _vector_hits(
        self,
        isolation_key: str,
        query: str,
        documents: Sequence[RagDocument],
        limit: int,
    ) -> tuple[list[ScreenwritingRagHit], str | None]:
        if not query or not self.vector_ready:
            return [], None
        document_by_id = {document.source_id: document for document in documents}
        try:
            chunks = self.vector_memory.query(isolation_key, query, limit=max(limit * 3, limit))
        except Exception as exc:
            return [], f"vector query failed: {exc}"
        hits: list[ScreenwritingRagHit] = []
        seen_source_ids: set[str] = set()
        for chunk in chunks:
            source_id = str(chunk.metadata.get("source_id") or "")
            document = document_by_id.get(source_id)
            if document is None or source_id in seen_source_ids:
                continue
            if float(chunk.score) < self.min_vector_score:
                continue
            source_type = str(chunk.metadata.get("source_type") or document.source_type)
            if source_type != document.source_type:
                continue
            seen_source_ids.add(source_id)
            hits.append(_rag_hit_from_chunk(document, chunk))
            if len(hits) >= limit:
                break
        return hits, None

    def _runtime_metadata(self) -> dict[str, Any]:
        runtime_metadata = getattr(self.vector_memory, "runtime_metadata", None)
        if callable(runtime_metadata):
            return dict(runtime_metadata())
        return {
            "assetsReady": self.vector_ready,
            "vectorReady": self.vector_ready,
            "retrievalMode": "vector" if self.vector_ready else "lexical_fallback",
            "failureReason": None,
        }


def _chunk_documents(
    documents: Sequence[RagDocument],
    *,
    chunk_chars: int,
    chunk_overlap: int,
) -> list[dict[str, Any]]:
    return list(_iter_document_chunks(documents, chunk_chars=chunk_chars, chunk_overlap=chunk_overlap))


def _iter_chunk_payload_batches(
    documents: Sequence[RagDocument],
    *,
    isolation_key: str,
    chunk_chars: int,
    chunk_overlap: int,
    chunk_batch_size: int,
) -> Iterator[tuple[list[str], list[dict[str, Any]], list[str]]]:
    chunk_documents: list[str] = []
    chunk_metadata: list[dict[str, Any]] = []
    chunk_ids: list[str] = []
    for chunk in _iter_document_chunks(documents, chunk_chars=chunk_chars, chunk_overlap=chunk_overlap):
        chunk_documents.append(str(chunk["content"]))
        chunk_metadata.append(dict(chunk["metadata"]))
        chunk_ids.append(f"{isolation_key}:{chunk['chunk_id']}")
        if len(chunk_documents) >= chunk_batch_size:
            yield chunk_documents, chunk_metadata, chunk_ids
            chunk_documents = []
            chunk_metadata = []
            chunk_ids = []
    if chunk_documents:
        yield chunk_documents, chunk_metadata, chunk_ids


def _iter_document_chunks(
    documents: Sequence[RagDocument],
    *,
    chunk_chars: int,
    chunk_overlap: int,
) -> Iterator[dict[str, Any]]:
    for document in documents:
        text_chunks = _chunk_text(document.content, chunk_chars=chunk_chars, chunk_overlap=chunk_overlap)
        chunk_count = len(text_chunks)
        for chunk_index, chunk_text in enumerate(text_chunks):
            yield {
                "chunk_id": _chunk_id(document.source_id, chunk_index),
                "content": chunk_text,
                "metadata": {
                    **document.metadata,
                    "source_id": document.source_id,
                    "source_type": document.source_type,
                    "title": document.title,
                    "chunk_index": chunk_index,
                    "chunk_count": chunk_count,
                    CHUNK_CONTENT_HASH_METADATA_KEY: _chunk_content_hash(chunk_text),
                },
            }


def _chunk_text(text: str, *, chunk_chars: int, chunk_overlap: int) -> list[str]:
    content = text.strip()
    if not content:
        return []
    if len(content) <= chunk_chars:
        return [content]
    overlap = min(max(0, chunk_overlap), max(0, chunk_chars - 1))
    step = max(1, chunk_chars - overlap)
    chunks: list[str] = []
    start = 0
    while start < len(content):
        chunk = content[start : start + chunk_chars].strip()
        if chunk:
            chunks.append(chunk)
        if start + chunk_chars >= len(content):
            break
        start += step
    return chunks


def _chunk_id(source_id: str, chunk_index: int) -> str:
    digest = hashlib.sha256(source_id.encode("utf-8")).hexdigest()[:16]
    return f"{digest}:{chunk_index}"


def _chunk_content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _rag_hit_from_chunk(document: RagDocument, chunk: RetrievedChunk) -> ScreenwritingRagHit:
    return ScreenwritingRagHit(
        document=document,
        score=round(float(chunk.score), 6),
        chunk_text=chunk.document,
        metadata=dict(chunk.metadata),
    )


def _lexical_fallback_hits(query: str, documents: Sequence[RagDocument], *, limit: int) -> list[ScreenwritingRagHit]:
    if not query:
        return []
    scored: list[tuple[float, int, RagDocument]] = []
    for index, document in enumerate(documents):
        score = lexical_score(query, f"{document.title}\n{document.content}".strip())
        if score <= 0:
            continue
        scored.append((score, index, document))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [
        ScreenwritingRagHit(
            document=document,
            score=round(float(score), 6),
            chunk_text=_fallback_context(document.content),
            metadata=dict(document.metadata),
        )
        for score, _, document in scored[:limit]
    ]


def _fallback_context(content: str) -> str:
    text = content.strip()
    if len(text) <= LEXICAL_CONTEXT_CHARS:
        return text
    return f"{text[:LEXICAL_CONTEXT_CHARS].strip()}..."


def _runtime_with_failure(runtime: Mapping[str, Any], failure_reason: str | None) -> dict[str, Any]:
    resolved = dict(runtime)
    if failure_reason:
        current_failure = str(resolved.get("failureReason") or "")
        resolved["failureReason"] = (
            f"{current_failure}; {failure_reason}"
            if current_failure
            else failure_reason
        )
    return resolved


def _format_context_text(hits: Sequence[ScreenwritingRagHit]) -> str:
    if not hits:
        return ""
    blocks = []
    for index, hit in enumerate(hits, start=1):
        label = _source_label(hit.document.source_type)
        blocks.append(
            "\n".join(
                part
                for part in (
                    f"[{index}] {label}: {hit.document.title}",
                    f"score: {hit.score:.6f}",
                    hit.chunk_text,
                )
                if part
            )
        )
    return "\n\n".join(blocks)


def _source_label(source_type: str) -> str:
    if source_type == "project":
        return "项目基础信息"
    if source_type == "novel":
        return "小说基础信息"
    if source_type == "chapter":
        return "章节资料"
    if source_type == "art_style":
        return "视觉风格"
    if source_type == "director_manual":
        return "导演手册"
    return source_type
