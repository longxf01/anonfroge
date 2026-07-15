from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from datetime import datetime
from time import perf_counter, time
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.harness import HarnessAgent, ScriptAgentEvent, ScriptAgentInput
from app.core.harness.runtime.deepagents import DeepAgentsRuntime
from app.core.harness.tools.adapter import ModelGatewayAdapter
from app.schemas.screenwriting import (
    ScreenwritingActiveTab,
    ScreenwritingChatPayload,
    ScreenwritingChatResponse,
    ScreenwritingChatTurn,
    ScreenwritingRagWarmupResponse,
    ScreenwritingStreamEvent,
)
from app.services import project as project_service
from app.services.screenwriting.prompts import build_guide_system_prompt
from app.services.screenwriting.rag_index import ScreenwritingRagContext
from app.services.screenwriting.rag_runtime import (
    build_rag_tools,
    build_system_prompt_with_rag,
    prepare_rag_context,
    rag_runtime_payload,
    schedule_rag_index_warmup,
)


MAX_HISTORY_MESSAGES = 40


class ScreenwritingServiceError(Exception):
    """剧本创作服务层基础异常。"""


class ScreenwritingValidationError(ScreenwritingServiceError):
    """剧本创作请求不合法。"""


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
    try:
        context = await _prepare_chat_context(
            session,
            project_public_id,
            current_user_public_id,
            payload,
            agent_factory=agent_factory,
        )
        agent_run_started_at = perf_counter()
        try:
            result = await context.agent.run_chat(context.agent_input())
        finally:
            context.server_timings.mark("agentRun", agent_run_started_at)
        content = result.content.strip()
        if not content:
            status = "empty_response"
            raise ScreenwritingServiceError("模型未返回可用对话内容")

        response = ScreenwritingChatResponse(
            conversation_id=context.conversation_id,
            isolation_key=context.isolation_key,
            model_id=context.model_id,
            active_tab=context.active_tab,
            content=content,
            messages=_response_messages(payload, content),
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
    """构建剧本创作多轮对话流式事件。"""
    context = await _prepare_chat_context(
        session,
        project_public_id,
        current_user_public_id,
        payload,
        agent_factory=agent_factory,
    )
    return _stream_prepared_chat(context)


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
        yield _stream_event(context, "start")

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
        yield _stream_event(
            context,
            "done",
            content=final_content,
            data={
                "assistantMessage": final_content,
                "messages": [
                    message.model_dump(by_alias=True, mode="json")
                    for message in _response_messages(context.payload, final_content)
                ],
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
    server_timings = ScreenwritingServerTimings.start(payload.client_request_started_at_ms)
    thinking_started_at = server_timings.started_at
    project_started_at = perf_counter()
    project = await project_service.get_project_or_raise(session, project_public_id, current_user_public_id)
    model_id = str(project.text_model or "").strip()
    if not model_id:
        raise ScreenwritingValidationError("项目尚未配置文本模型，请先在项目设置中选择文本模型")
    server_timings.mark("project", project_started_at)

    conversation_id = _resolve_conversation_id(payload)
    isolation_key = _build_isolation_key(project_public_id, current_user_public_id, conversation_id)
    active_tab = payload.active_tab
    rag_started_at = perf_counter()
    rag_preparation = await prepare_rag_context(session, project, project_public_id, payload.message)
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
        messages=_agent_messages(payload),
        payload=payload,
        rag_context=rag_preparation.context,
        rag_document_count=rag_preparation.document_count,
        thinking_started_at=thinking_started_at,
        server_timings=server_timings,
        agent=agent,
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


def _agent_messages(payload: ScreenwritingChatPayload) -> list[dict[str, str]]:
    messages = [
        {"role": message.role, "content": message.content}
        for message in payload.messages[-MAX_HISTORY_MESSAGES:]
        if message.content.strip()
    ]
    messages.append({"role": "user", "content": payload.message.strip()})
    return messages


def _response_messages(payload: ScreenwritingChatPayload, assistant_content: str) -> list[ScreenwritingChatTurn]:
    return [
        *payload.messages[-MAX_HISTORY_MESSAGES:],
        ScreenwritingChatTurn(role="user", content=payload.message, time=_format_chat_time()),
        ScreenwritingChatTurn(role="assistant", content=assistant_content, time=_format_chat_time()),
    ]


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


def _resolve_conversation_id(payload: ScreenwritingChatPayload) -> str:
    if payload.reset or not payload.conversation_id:
        return uuid4().hex
    return payload.conversation_id


def _build_isolation_key(project_public_id: str, user_public_id: str, conversation_id: str) -> str:
    return f"screenwriting:{project_public_id}:{user_public_id}:{conversation_id}"


def _format_chat_time(now: datetime | None = None) -> str:
    try:
        tz = ZoneInfo(settings.tz)
    except ZoneInfoNotFoundError:
        tz = None
    current = now or datetime.now(tz)
    return current.strftime("%H:%M")
