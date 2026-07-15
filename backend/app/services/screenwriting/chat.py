from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.harness import DeepAgentsRuntime, HarnessAgent, ModelGatewayAdapter, ScriptAgentEvent, ScriptAgentInput
from app.schemas.screenwriting import (
    ScreenwritingActiveTab,
    ScreenwritingChatPayload,
    ScreenwritingChatResponse,
    ScreenwritingChatTurn,
    ScreenwritingStreamEvent,
)
from app.services import project as project_service
from app.services.screenwriting.prompts import build_guide_system_prompt


MAX_HISTORY_MESSAGES = 40


class ScreenwritingServiceError(Exception):
    """剧本创作服务层基础异常。"""


class ScreenwritingValidationError(ScreenwritingServiceError):
    """剧本创作请求不合法。"""


ScreenwritingAgentFactory = Callable[..., HarnessAgent]


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
    agent: HarnessAgent

    def agent_input(self) -> ScriptAgentInput:
        """转换为 Harness Agent 单次调用输入。"""
        return ScriptAgentInput(
            project_public_id=self.project_public_id,
            user_public_id=self.user_public_id,
            isolation_key=self.isolation_key,
            messages=self.messages,
            model_id=self.model_id,
            metadata={
                "conversation_id": self.conversation_id,
                "active_tab": self.active_tab,
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
    context = await _prepare_chat_context(
        session,
        project_public_id,
        current_user_public_id,
        payload,
        agent_factory=agent_factory,
    )
    result = await context.agent.run_chat(context.agent_input())
    content = result.content.strip()
    if not content:
        raise ScreenwritingServiceError("模型未返回可用对话内容")

    return ScreenwritingChatResponse(
        conversation_id=context.conversation_id,
        isolation_key=context.isolation_key,
        model_id=context.model_id,
        active_tab=context.active_tab,
        content=content,
        messages=_response_messages(payload, content),
        runtime={
            "agent": "harness",
            "conversation": "multi_turn",
        },
    )


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


async def _stream_prepared_chat(context: ScreenwritingChatContext) -> AsyncIterator[ScreenwritingStreamEvent]:
    yield _stream_event(context, "start")

    content = ""
    try:
        async for event in context.agent.stream_chat(context.agent_input()):
            if event.type == "message.delta":
                delta = _normalize_agent_delta(content, event.content)
                if not delta:
                    continue
                content += delta
                yield _stream_event(context, event.type, content=delta, data=event.data)
                continue
            yield _event_from_agent_event(context, event)
    except Exception as exc:
        yield _stream_event(
            context,
            "error",
            data={"detail": str(exc), "errorType": exc.__class__.__name__},
        )
        return

    final_content = content.strip()
    if not final_content:
        yield _stream_event(
            context,
            "error",
            data={"detail": "模型未返回可用对话内容", "errorType": "ScreenwritingServiceError"},
        )
        return

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


async def _prepare_chat_context(
    session: AsyncSession,
    project_public_id: str,
    current_user_public_id: str,
    payload: ScreenwritingChatPayload,
    *,
    agent_factory: ScreenwritingAgentFactory | None,
) -> ScreenwritingChatContext:
    project = await project_service.get_project_or_raise(session, project_public_id, current_user_public_id)
    model_id = str(project.text_model or "").strip()
    if not model_id:
        raise ScreenwritingValidationError("项目尚未配置文本模型，请先在项目设置中选择文本模型")

    conversation_id = _resolve_conversation_id(payload)
    isolation_key = _build_isolation_key(project_public_id, current_user_public_id, conversation_id)
    active_tab = payload.active_tab
    return ScreenwritingChatContext(
        project_public_id=project_public_id,
        user_public_id=current_user_public_id,
        conversation_id=conversation_id,
        isolation_key=isolation_key,
        model_id=model_id,
        active_tab=active_tab,
        messages=_agent_messages(payload),
        payload=payload,
        agent=(agent_factory or _default_agent_factory)(
            model_id=model_id,
            system_prompt=build_guide_system_prompt(active_tab),
        ),
    )


def _default_agent_factory(*, model_id: str, system_prompt: str) -> HarnessAgent:
    runtime = DeepAgentsRuntime(
        adapter=ModelGatewayAdapter(default_model_id=model_id),
        model_id=model_id,
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
    if incoming_content.startswith(current_content):
        return incoming_content[len(current_content) :]
    if incoming_content in current_content:
        return ""
    return incoming_content


def _event_from_agent_event(context: ScreenwritingChatContext, event: ScriptAgentEvent) -> ScreenwritingStreamEvent:
    return _stream_event(
        context,
        event.type,
        content=event.content,
        data=event.data,
    )


def _stream_event(
    context: ScreenwritingChatContext,
    event_type: str,
    *,
    content: str = "",
    data: dict[str, Any] | None = None,
) -> ScreenwritingStreamEvent:
    return ScreenwritingStreamEvent(
        type=event_type,
        content=content,
        conversation_id=context.conversation_id,
        isolation_key=context.isolation_key,
        model_id=context.model_id,
        active_tab=context.active_tab,
        data=data or {},
    )


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
