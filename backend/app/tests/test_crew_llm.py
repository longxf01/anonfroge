from __future__ import annotations

from typing import Any

import pytest

from app.core.harness.tools.crew_llm import CrewAIBaseLLM, ProviderGatewayCrewLLM


class StubModelGatewayAdapter:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def generate_response(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return {"choices": [{"message": {"content": "完整响应"}}]}

    async def generate_stream(self, **kwargs: Any):
        self.calls.append(kwargs)
        for chunk in ("流式", "响应"):
            yield chunk


def test_crewai_llm_uses_new_base_llm_constructor() -> None:
    adapter = StubModelGatewayAdapter()

    llm = ProviderGatewayCrewLLM(
        adapter=adapter,
        model="test-model",
        stream=True,
        request_options={"temperature": 0.2},
    )

    assert CrewAIBaseLLM is not None
    assert isinstance(llm, CrewAIBaseLLM)
    assert llm.model == "test-model"
    assert llm.adapter is adapter
    assert llm.stream is True
    assert llm.request_options == {"temperature": 0.2}


@pytest.mark.anyio
async def test_crewai_llm_calls_project_gateway() -> None:
    adapter = StubModelGatewayAdapter()
    llm = ProviderGatewayCrewLLM(
        adapter=adapter,
        model="test-model",
        request_options={"temperature": 0.2},
    )

    result = await llm.acall("你好")

    assert result == "完整响应"
    assert adapter.calls == [
        {
            "model_id": "test-model",
            "messages": [{"role": "user", "content": "你好"}],
            "temperature": 0.2,
        }
    ]


@pytest.mark.anyio
async def test_crewai_llm_streams_through_project_gateway(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = StubModelGatewayAdapter()
    emitted_chunks: list[str] = []
    llm = ProviderGatewayCrewLLM(
        adapter=adapter,
        model="test-model",
        stream=True,
    )
    monkeypatch.setattr(
        llm,
        "_emit_stream_chunk_event",
        lambda chunk, **_: emitted_chunks.append(chunk),
    )

    result = await llm.acall([{"role": "user", "content": "生成故事骨架"}])

    assert result == "流式响应"
    assert emitted_chunks == ["流式", "响应"]
