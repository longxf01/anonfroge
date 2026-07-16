from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from time import perf_counter, time
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.harness import HarnessAgent, ScriptAgentEvent, ScriptAgentInput
from app.core.harness.runtime.deepagents import DeepAgentsRuntime
from app.core.harness.tools.adapter import ModelGatewayAdapter
from app.schemas.screenwriting import (
    ScreenwritingActiveTab,
    ScreenwritingChatPayload,
    ScreenwritingChatResponse,
    ScreenwritingRagWarmupResponse,
    ScreenwritingStreamEvent,
)
from app.services import project as project_service
from app.services.screenwriting.errors import (
    ScreenwritingServiceError,
    ScreenwritingValidationError,
)
from app.services.screenwriting.prompts import build_guide_system_prompt
from app.services.screenwriting.query_intent import normalize_lookup_text
from app.services.screenwriting.rag_index import ScreenwritingRagContext
from app.services.screenwriting.rag_runtime import (
    build_rag_tools,
    build_system_prompt_with_rag,
    prepare_rag_context,
    rag_runtime_payload,
    schedule_rag_index_warmup,
)
from app.services.screenwriting.state import (
    ScreenwritingSessionState,
    acquire_session_lock,
    commit_chat_turns,
    load_chat_session_state,
)


MAX_HISTORY_MESSAGES = 40

__all__ = [
    "ScreenwritingServiceError",
    "ScreenwritingValidationError",
    "chat_screenwriting",
    "build_screenwriting_chat_stream",
    "warmup_screenwriting_rag_index",
]


ScreenwritingAgentFactory = Callable[..., HarnessAgent]


@dataclass
class ScreenwritingServerTimings:
    """单次请求在服务端的阶段耗时。"""

    started_at: float
    server_started_at_ms: int
    client_request_started_at_ms: int | None = None
    stages: list[dict[str, int | str]] = field(default_factory=list)

    @classmethod
    def start(cls, client_request_started_at_ms: int | None = None) -> "ScreenwritingServerTimings":
        return cls(
            started_at=perf_counter(),
            server_started_at_ms=int(time() * 1000),
            client_request_started_at_ms=client_request_started_at_ms,
        )

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
        client_to_server_ms = None
        if self.client_request_started_at_ms is not None:
            client_to_server_ms = max(0, self.server_started_at_ms - self.client_request_started_at_ms)
        return {
            "totalMs": _duration_ms(self.started_at, perf_counter()),
            "clientToServerMs": client_to_server_ms,
            "stages": [dict(stage) for stage in self.stages],
        }


@dataclass(frozen=True)
class ScreenwritingChatContext:
    """单次剧本创作对话上下文。"""

    project_public_id: str
    user_public_id: str
    conversation_id: str
    isolation_key: str
    model_id: str
    active_tab: ScreenwritingActiveTab
    messages: list[dict[str, str]]
    payload: ScreenwritingChatPayload
    rag_context: ScreenwritingRagContext
    rag_document_count: int
    thinking_started_at: float
    server_timings: ScreenwritingServerTimings
    agent: HarnessAgent
    db_session: AsyncSession
    project: Any
    session_state: ScreenwritingSessionState

    def agent_input(self) -> ScriptAgentInput:
        """转换为 Harness Agent 单次调用输入。"""
        rag_runtime = rag_runtime_payload(self.rag_context, document_count=self.rag_document_count)
        return ScriptAgentInput(
            project_public_id=self.project_public_id,
            user_public_id=self.user_public_id,
            isolation_key=self.isolation_key,
            messages=self.messages,
            model_id=self.model_id,
            metadata={
                "conversation_id": self.conversation_id,
                "active_tab": self.active_tab,
                "rag": rag_runtime,
            },
        )


async def chat_screenwriting(
    session: AsyncSession,
    project_public_id: str,
    current_user_public_id: str,
    payload: ScreenwritingChatPayload,
    *,
    agent_factory: ScreenwritingAgentFactory | None = None,
) -> ScreenwritingChatResponse:
    """执行一次剧本创作多轮对话，并返回聚合响应。"""
    context: ScreenwritingChatContext | None = None
    status = "error"
    lock = await acquire_session_lock(project_public_id, current_user_public_id)
    async with lock:
        try:
            context = await _prepare_chat_context(
                session,
                project_public_id,
                current_user_public_id,
                payload,
                agent_factory=agent_factory,
            )
            direct_answer_started_at = perf_counter()
            direct_answer = _metadata_direct_answer(context)
            if direct_answer:
                context.server_timings.mark("directAnswer", direct_answer_started_at)
                state = await commit_chat_turns(
                    session,
                    context.project,
                    context.session_state,
                    user_content=payload.message,
                    assistant_content=direct_answer,
                    active_tab=payload.active_tab,
                )
                response = ScreenwritingChatResponse(
                    conversation_id=context.conversation_id,
                    isolation_key=context.isolation_key,
                    model_id=context.model_id,
                    active_tab=context.active_tab,
                    content=direct_answer,
                    messages=list(state.messages),
                    runtime={
                        "agent": "metadata_direct",
                        "conversation": "multi_turn",
                        "rag": rag_runtime_payload(context.rag_context, document_count=context.rag_document_count),
                        "directAnswer": True,
                        "thinkingElapsedMs": _thinking_elapsed_ms(context),
                        "serverTimings": context.server_timings.payload(),
                    },
                )
                status = "completed"
                return response

            agent_run_started_at = perf_counter()
            try:
                result = await context.agent.run_chat(context.agent_input())
            finally:
                context.server_timings.mark("agentRun", agent_run_started_at)
            content = result.content.strip()
            if not content:
                status = "empty_response"
                raise ScreenwritingServiceError("模型未返回可用对话内容")

            state = await commit_chat_turns(
                session,
                context.project,
                context.session_state,
                user_content=payload.message,
                assistant_content=content,
                active_tab=payload.active_tab,
            )
            response = ScreenwritingChatResponse(
                conversation_id=context.conversation_id,
                isolation_key=context.isolation_key,
                model_id=context.model_id,
                active_tab=context.active_tab,
                content=content,
                messages=list(state.messages),
                runtime={
                    "agent": "harness",
                    "conversation": "multi_turn",
                    "rag": rag_runtime_payload(context.rag_context, document_count=context.rag_document_count),
                    "thinkingElapsedMs": _thinking_elapsed_ms(context),
                    "serverTimings": context.server_timings.payload(),
                },
            )
            status = "completed"
            return response
        finally:
            if context is not None:
                _print_server_timing_log(context, operation="chat", status=status)


async def build_screenwriting_chat_stream(
    session: AsyncSession,
    project_public_id: str,
    current_user_public_id: str,
    payload: ScreenwritingChatPayload,
    *,
    agent_factory: ScreenwritingAgentFactory | None = None,
) -> AsyncIterator[ScreenwritingStreamEvent]:
    """构建剧本创作多轮对话流式事件。

    本函数是异步生成器：首个 start(preparing) 事件在项目加载与 RAG 准备
    开始前即发出，保证客户端立即获得服务端反馈；准备阶段的任何异常都
    转换为 error 事件而不是 HTTP 异常。整个生成期间持有会话锁，使同一
    会话的流式对话串行执行。
    """
    server_timings = ScreenwritingServerTimings.start(payload.client_request_started_at_ms)
    yield ScreenwritingStreamEvent(
        type="start",
        content="",
        conversation_id="",
        isolation_key="",
        model_id="",
        active_tab=payload.active_tab,
        data={
            "phase": "preparing",
            "thinkingElapsedMs": _elapsed_ms_since(server_timings.started_at),
            "serverTimings": server_timings.payload(),
        },
    )
    lock = await acquire_session_lock(project_public_id, current_user_public_id)
    async with lock:
        try:
            project, model_id = await _load_chat_project(
                session,
                project_public_id,
                current_user_public_id,
                server_timings,
            )
            state = await load_chat_session_state(
                session,
                project,
                project_public_id,
                current_user_public_id,
                reset=payload.reset,
            )
            context = await _build_chat_context(
                session,
                project,
                project_public_id,
                current_user_public_id,
                payload,
                model_id=model_id,
                state=state,
                server_timings=server_timings,
                agent_factory=agent_factory,
            )
        except Exception as exc:
            yield ScreenwritingStreamEvent(
                type="error",
                content="",
                conversation_id="",
                isolation_key="",
                model_id="",
                active_tab=payload.active_tab,
                data={
                    "detail": _exception_detail(exc),
                    "errorType": exc.__class__.__name__,
                    "thinkingElapsedMs": _elapsed_ms_since(server_timings.started_at),
                    "serverTimings": server_timings.payload(),
                },
            )
            return
        async for event in _stream_prepared_chat(context):
            yield event


async def warmup_screenwriting_rag_index(
    session: AsyncSession,
    project_public_id: str,
    current_user_public_id: str,
) -> ScreenwritingRagWarmupResponse:
    """校验项目访问权限后异步调度剧本创作 RAG 向量索引预热。"""
    await project_service.get_project_or_raise(session, project_public_id, current_user_public_id)
    schedule = schedule_rag_index_warmup(project_public_id, current_user_public_id)
    return ScreenwritingRagWarmupResponse(
        status=schedule.status,
        rag_isolation_key=schedule.rag_isolation_key,
    )


async def _stream_prepared_chat(context: ScreenwritingChatContext) -> AsyncIterator[ScreenwritingStreamEvent]:
    status = "cancelled"
    content = ""
    model_stream_started_at: float | None = None
    model_stream_marked = False

    def mark_model_stream() -> None:
        nonlocal model_stream_marked
        if model_stream_marked or model_stream_started_at is None:
            return
        context.server_timings.mark("modelStream", model_stream_started_at)
        model_stream_marked = True

    try:
        direct_answer_started_at = perf_counter()
        direct_answer = _metadata_direct_answer(context)
        if direct_answer:
            context.server_timings.mark("directAnswer", direct_answer_started_at)
            status = "completed"
            state = await commit_chat_turns(
                context.db_session,
                context.project,
                context.session_state,
                user_content=context.payload.message,
                assistant_content=direct_answer,
                active_tab=context.payload.active_tab,
            )
            yield _stream_event(
                context,
                "done",
                content=direct_answer,
                data={
                    "directAnswer": True,
                    "assistantMessage": direct_answer,
                    "messages": _state_message_payload(state),
                },
            )
            return

        model_stream_started_at = perf_counter()
        try:
            async for event in context.agent.stream_chat(context.agent_input()):
                if event.type == "message.delta":
                    delta = _normalize_agent_delta(content, event.content)
                    if not delta:
                        continue
                    content += delta
                    yield _stream_event(context, event.type, content=delta, data=event.data)
                    continue
                if event.type == "done":
                    final_content = _agent_final_content(event)
                    if final_content:
                        content += _normalize_agent_delta(content, final_content)
                    break
                if event.type == "error":
                    mark_model_stream()
                    status = "error"
                    yield _agent_error_event(context, event)
                    return
                yield _event_from_agent_event(context, event)
        except Exception as exc:
            mark_model_stream()
            status = "error"
            yield _stream_event(
                context,
                "error",
                data={"detail": _exception_detail(exc), "errorType": exc.__class__.__name__},
            )
            return

        mark_model_stream()
        final_content = content.strip()
        if not final_content:
            status = "empty_response"
            yield _stream_event(
                context,
                "error",
                data={"detail": "模型未返回可用对话内容", "errorType": "ScreenwritingServiceError"},
            )
            return

        status = "completed"
        state = await commit_chat_turns(
            context.db_session,
            context.project,
            context.session_state,
            user_content=context.payload.message,
            assistant_content=final_content,
            active_tab=context.payload.active_tab,
        )
        yield _stream_event(
            context,
            "done",
            content=final_content,
            data={
                "assistantMessage": final_content,
                "messages": _state_message_payload(state),
            },
        )
    finally:
        mark_model_stream()
        _print_server_timing_log(context, operation="chat.stream", status=status)


async def _prepare_chat_context(
    session: AsyncSession,
    project_public_id: str,
    current_user_public_id: str,
    payload: ScreenwritingChatPayload,
    *,
    agent_factory: ScreenwritingAgentFactory | None,
) -> ScreenwritingChatContext:
    """准备聚合对话上下文；调用方必须已持有会话锁。"""
    server_timings = ScreenwritingServerTimings.start(payload.client_request_started_at_ms)
    project, model_id = await _load_chat_project(
        session,
        project_public_id,
        current_user_public_id,
        server_timings,
    )
    state = await load_chat_session_state(
        session,
        project,
        project_public_id,
        current_user_public_id,
        reset=payload.reset,
    )
    return await _build_chat_context(
        session,
        project,
        project_public_id,
        current_user_public_id,
        payload,
        model_id=model_id,
        state=state,
        server_timings=server_timings,
        agent_factory=agent_factory,
    )


async def _load_chat_project(
    session: AsyncSession,
    project_public_id: str,
    current_user_public_id: str,
    server_timings: ScreenwritingServerTimings,
) -> tuple[Any, str]:
    """加载项目并校验文本模型配置；访问类异常在此抛出以映射为 HTTP 错误。"""
    project_started_at = perf_counter()
    project = await project_service.get_project_or_raise(session, project_public_id, current_user_public_id)
    model_id = str(project.text_model or "").strip()
    if not model_id:
        raise ScreenwritingValidationError("项目尚未配置文本模型，请先在项目设置中选择文本模型")
    server_timings.mark("project", project_started_at)
    return project, model_id


async def _build_chat_context(
    session: AsyncSession,
    project: Any,
    project_public_id: str,
    current_user_public_id: str,
    payload: ScreenwritingChatPayload,
    *,
    model_id: str,
    state: ScreenwritingSessionState,
    server_timings: ScreenwritingServerTimings,
    agent_factory: ScreenwritingAgentFactory | None,
) -> ScreenwritingChatContext:
    active_tab = payload.active_tab
    conversation_id = state.conversation_id
    isolation_key = _build_isolation_key(project_public_id, current_user_public_id, conversation_id)
    rag_started_at = perf_counter()
    rag_preparation = await prepare_rag_context(
        session,
        project,
        project_public_id,
        current_user_public_id,
        payload.message,
    )
    server_timings.mark("rag", rag_started_at)
    agent_setup_started_at = perf_counter()
    tools = build_rag_tools(rag_preparation.context)
    system_prompt = build_system_prompt_with_rag(build_guide_system_prompt(active_tab), rag_preparation.context)
    agent = (agent_factory or _default_agent_factory)(
        model_id=model_id,
        system_prompt=system_prompt,
        tools=tools,
    )
    server_timings.mark("agentSetup", agent_setup_started_at)
    return ScreenwritingChatContext(
        project_public_id=project_public_id,
        user_public_id=current_user_public_id,
        conversation_id=conversation_id,
        isolation_key=isolation_key,
        model_id=model_id,
        active_tab=active_tab,
        messages=_agent_messages(state, payload),
        payload=payload,
        rag_context=rag_preparation.context,
        rag_document_count=rag_preparation.document_count,
        thinking_started_at=server_timings.started_at,
        server_timings=server_timings,
        agent=agent,
        db_session=session,
        project=project,
        session_state=state,
    )


def _default_agent_factory(
    *,
    model_id: str,
    system_prompt: str,
    tools: list[Callable[..., Any]] | None = None,
) -> HarnessAgent:
    runtime = DeepAgentsRuntime(
        adapter=ModelGatewayAdapter(default_model_id=model_id),
        model_id=model_id,
        tools=tools,
        system_prompt=system_prompt,
    )
    return HarnessAgent(runtime=runtime)


def _agent_messages(state: ScreenwritingSessionState, payload: ScreenwritingChatPayload) -> list[dict[str, str]]:
    """从服务端会话状态构造 Agent 输入消息（截取最近若干轮 + 本轮输入）。"""
    messages = [
        {"role": turn.role, "content": turn.content}
        for turn in state.messages[-MAX_HISTORY_MESSAGES:]
        if turn.content.strip()
    ]
    messages.append({"role": "user", "content": payload.message.strip()})
    return messages


def _state_message_payload(state: ScreenwritingSessionState) -> list[dict[str, str]]:
    return [message.model_dump(by_alias=True, mode="json") for message in state.messages]


def _metadata_direct_answer(context: ScreenwritingChatContext) -> str:
    """对确定性的 metadata 字段查询直接返回命中字段，避免简单问题等待模型生成。"""
    rag_context = context.rag_context
    runtime = rag_context.runtime
    if runtime.get("retrievalMode") != "metadata":
        return ""
    if runtime.get("retrievalStrategy") != "field_lookup_exact":
        return ""

    lookup_specs = _runtime_field_lookup_specs(runtime)
    if not lookup_specs:
        return ""

    answer_lines: list[str] = []
    for hit in rag_context.hits:
        markers = [
            marker
            for source_type, source_markers in lookup_specs
            if source_type == hit.document.source_type
            for marker in source_markers
        ]
        if not markers:
            continue
        answer_lines.extend(_matching_field_lines(hit.chunk_text, markers))

    return "\n".join(_dedupe_preserve_order(answer_lines[:5]))


def _runtime_field_lookup_specs(runtime: dict[str, Any]) -> list[tuple[str, tuple[str, ...]]]:
    raw_specs = runtime.get("intentFieldLookups")
    if not isinstance(raw_specs, list):
        return []
    specs: list[tuple[str, tuple[str, ...]]] = []
    for raw_spec in raw_specs:
        if not isinstance(raw_spec, dict):
            continue
        source_type = str(raw_spec.get("sourceType") or raw_spec.get("source_type") or "").strip()
        raw_markers = raw_spec.get("documentMarkers") or raw_spec.get("document_markers")
        if not source_type or not isinstance(raw_markers, list):
            continue
        markers = tuple(str(marker).strip() for marker in raw_markers if str(marker).strip())
        if markers:
            specs.append((source_type, markers))
    return specs


def _matching_field_lines(text: str, markers: list[str]) -> list[str]:
    normalized_markers = tuple(normalize_lookup_text(marker) for marker in markers)
    lines: list[str] = []
    for raw_line in str(text or "").splitlines():
        label, value = _split_field_line(raw_line)
        if not label or not value:
            continue
        normalized_label = normalize_lookup_text(label)
        if not any(marker and marker in normalized_label for marker in normalized_markers):
            continue
        lines.append(f"{label.strip()}: {value.strip()}")
    return lines


def _split_field_line(line: str) -> tuple[str, str]:
    text = str(line or "").strip()
    for delimiter in ("：", ":"):
        if delimiter in text:
            label, value = text.split(delimiter, 1)
            return label.strip(), value.strip()
    return "", ""


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _normalize_agent_delta(current_content: str, incoming_content: str) -> str:
    """把运行时可能返回的累计内容转换为客户端可直接追加的增量。"""
    if not incoming_content:
        return ""
    if not current_content:
        return incoming_content
    if len(incoming_content) > len(current_content) and incoming_content.startswith(current_content):
        return incoming_content[len(current_content) :]
    return incoming_content


def _event_from_agent_event(context: ScreenwritingChatContext, event: ScriptAgentEvent) -> ScreenwritingStreamEvent:
    return _stream_event(
        context,
        event.type,
        content=event.content,
        data=event.data,
    )


def _agent_error_event(context: ScreenwritingChatContext, event: ScriptAgentEvent) -> ScreenwritingStreamEvent:
    data = dict(event.data)
    data["detail"] = _agent_error_detail(event)
    data.setdefault("errorType", "AgentRuntimeError")
    return _stream_event(context, "error", content=event.content, data=data)


def _agent_error_detail(event: ScriptAgentEvent) -> str:
    for key in ("detail", "message", "errorMessage", "error", "reason"):
        value = event.data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    if event.content.strip():
        return event.content.strip()
    return "Agent 运行时返回错误事件"


def _agent_final_content(event: ScriptAgentEvent) -> str:
    if event.content.strip():
        return event.content.strip()
    for key in ("assistantMessage", "content", "message", "text", "answer"):
        value = event.data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    messages = event.data.get("messages")
    if isinstance(messages, list):
        for message in reversed(messages):
            if not isinstance(message, dict) or message.get("role") != "assistant":
                continue
            value = message.get("content")
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def _exception_detail(exc: Exception) -> str:
    detail = str(exc).strip()
    return detail or exc.__class__.__name__


def _stream_event(
    context: ScreenwritingChatContext,
    event_type: str,
    *,
    content: str = "",
    data: dict[str, Any] | None = None,
) -> ScreenwritingStreamEvent:
    event_data = dict(data or {})
    event_data.setdefault("thinkingElapsedMs", _thinking_elapsed_ms(context))
    event_data.setdefault("serverTimings", context.server_timings.payload())
    if event_type in {"start", "done", "error"}:
        event_data.setdefault(
            "rag",
            rag_runtime_payload(context.rag_context, document_count=context.rag_document_count),
        )
    return ScreenwritingStreamEvent(
        type=event_type,
        content=content,
        conversation_id=context.conversation_id,
        isolation_key=context.isolation_key,
        model_id=context.model_id,
        active_tab=context.active_tab,
        data=event_data,
    )


def _elapsed_ms_since(started_at: float) -> int:
    return max(0, int((perf_counter() - started_at) * 1000))


def _thinking_elapsed_ms(context: ScreenwritingChatContext) -> int:
    return max(0, int((perf_counter() - context.thinking_started_at) * 1000))


def _print_server_timing_log(context: ScreenwritingChatContext, *, operation: str, status: str) -> None:
    print(_format_server_timing_log(context, operation=operation, status=status), flush=True)


def _format_server_timing_log(context: ScreenwritingChatContext, *, operation: str, status: str) -> str:
    timings = context.server_timings.payload()
    stages = ", ".join(_format_timing_stage(stage) for stage in timings["stages"]) or "-"
    return (
        "Screenwriting server timings: "
        f"operation={operation} "
        f"status={status} "
        f"project_public_id={context.project_public_id} "
        f"conversation_id={context.conversation_id} "
        f"active_tab={context.active_tab} "
        f"model_id={context.model_id} "
        f"total_ms={timings['totalMs']} "
        f"client_to_server_ms={_format_optional_ms(timings['clientToServerMs'])} "
        f"rag_mode={context.rag_context.runtime.get('retrievalMode', '-')} "
        f"rag_hits={len(context.rag_context.hits)} "
        f"rag_documents={context.rag_document_count} "
        f"stages=[{stages}]"
    )


def _format_timing_stage(stage: dict[str, int | str]) -> str:
    return (
        f"{stage['name']}={stage['durationMs']}ms"
        f"(+{stage['startedAtMs']}..+{stage['endedAtMs']}ms)"
    )


def _format_optional_ms(value: int | None) -> str:
    if value is None:
        return "-"
    return f"{value}ms"


def _duration_ms(started_at: float, ended_at: float) -> int:
    return max(0, int((ended_at - started_at) * 1000))


def _build_isolation_key(project_public_id: str, user_public_id: str, conversation_id: str) -> str:
    return f"screenwriting:{project_public_id}:{user_public_id}:{conversation_id}"