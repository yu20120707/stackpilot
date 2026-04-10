import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.clients.llm_client import LLMClientError
from app.clients.feishu_client import FeishuClient
from app.models.contracts import (
    AnalysisRequest,
    AnalysisResultStatus,
    ConfidenceLevel,
    FeishuThreadLoadResponse,
    KnowledgeCitation,
    NormalizedFeishuMessageEvent,
    SourceType,
    StructuredSummary,
    ThreadMessage,
    TriggerCommand,
)
from app.services.analysis_service import AnalysisService
from app.services.reply_renderer import ReplyRenderer
from app.services.thread_reader import ThreadReader


FIXTURES_DIR = Path(__file__).parent / "fixtures"


class FakeFeishuClient(FeishuClient):
    def __init__(self, payload: dict) -> None:
        super().__init__()
        self.payload = payload

    async def fetch_thread_messages(
        self,
        *,
        chat_id: str,
        message_id: str,
        thread_id: str,
    ) -> FeishuThreadLoadResponse:
        _ = chat_id, message_id, thread_id
        return FeishuThreadLoadResponse.model_validate(self.payload)


class FakeLLMClient:
    def __init__(self, response: str | Exception) -> None:
        self.response = response
        self.calls: list[tuple[str, str]] = []

    async def generate_structured_summary(self, *, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def load_json(*parts: str) -> dict:
    return json.loads(FIXTURES_DIR.joinpath(*parts).read_text(encoding="utf-8"))


def build_trigger_event(trigger_text: str, *, thread_id: str = "omt_xxx") -> NormalizedFeishuMessageEvent:
    return NormalizedFeishuMessageEvent(
        chat_id="oc_xxx",
        message_id="om_trigger",
        thread_id=thread_id,
        sender_id="ou_xxx",
        sender_name="Alice",
        message_text=trigger_text,
        mentions_bot=True,
        event_time="2026-04-10T01:07:00+08:00",
    )


def build_citations() -> list[KnowledgeCitation]:
    return [
        KnowledgeCitation(
            source_type=SourceType.KNOWLEDGE_DOC,
            label="Payment Service SOP",
            source_uri="data/knowledge/payment-sop.md",
            snippet="When the payment service shows a 5xx spike after deployment...",
        )
    ]


@pytest.mark.anyio
async def test_thread_reader_extracts_follow_up_context_from_same_thread() -> None:
    reader = ThreadReader(FakeFeishuClient(load_json("feishu", "thread_messages_follow_up.json")))

    request = await reader.build_analysis_request(
        trigger_command=TriggerCommand.RERUN_ANALYSIS,
        trigger_event=build_trigger_event("@机器人 基于最新信息重试"),
    )

    assert request.follow_up_context is not None
    assert request.follow_up_context.previous_summary is not None
    assert "当前判断：" in request.follow_up_context.previous_summary
    assert [message.message_id for message in request.follow_up_context.new_messages] == ["om_2", "om_3"]


@pytest.mark.anyio
async def test_analysis_service_uses_follow_up_context_even_with_short_new_messages(tmp_path: Path) -> None:
    prompt_path = tmp_path / "analysis_prompt.md"
    prompt_path.write_text("Return structured JSON only.", encoding="utf-8")
    llm_client = FakeLLMClient(
        json.dumps(
            {
                "status": "success",
                "confidence": "medium",
                "current_assessment": "结合前一次结果和新补充信息，当前判断更偏向发布问题已缓解。",
                "known_facts": ["已执行回滚", "错误率继续下降"],
                "impact_scope": "当前影响范围较此前收敛，但仍需确认边界。",
                "next_actions": ["继续观察错误率", "补充错误日志"],
                "citations": [],
                "missing_information": ["详细错误日志"],
            },
            ensure_ascii=False,
        )
    )
    service = AnalysisService(llm_client, prompt_path=prompt_path)
    request = AnalysisRequest(
        trigger_command=TriggerCommand.RERUN_ANALYSIS,
        chat_id="oc_xxx",
        thread_id="omt_xxx",
        trigger_message_id="om_trigger",
        user_id="ou_xxx",
        user_display_name="Alice",
        thread_messages=[
            ThreadMessage(
                message_id="om_1",
                sender_name="Alice",
                sent_at=datetime.now(timezone.utc),
                text="补充信息：回滚后错误率继续下降",
            ),
            ThreadMessage(
                message_id="om_2",
                sender_name="Alice",
                sent_at=datetime.now(timezone.utc),
                text="@机器人 基于最新信息重试",
            ),
        ],
        follow_up_context={
            "previous_summary": "当前判断：支付服务异常可能与最近发布有关。",
            "new_messages": [
                {
                    "message_id": "om_1",
                    "sender_name": "Alice",
                    "sent_at": datetime.now(timezone.utc),
                    "text": "补充信息：回滚后错误率继续下降",
                }
            ],
        },
    )

    result = await service.summarize(request, citations=build_citations())

    assert result.status == AnalysisResultStatus.SUCCESS
    assert llm_client.calls
    assert "follow_up_context" in llm_client.calls[0][1]
    assert "previous_summary" in llm_client.calls[0][1]


def test_reply_renderer_adds_follow_up_prefix_for_rerun_analysis() -> None:
    renderer = ReplyRenderer()
    reply = StructuredSummary(
        status=AnalysisResultStatus.SUCCESS,
        confidence=ConfidenceLevel.MEDIUM,
        current_assessment="当前判断更偏向发布问题已缓解。",
        known_facts=["已执行回滚"],
        impact_scope="当前影响范围较此前收敛。",
        next_actions=["继续观察错误率"],
        citations=[],
        missing_information=[],
    )

    rendered = renderer.render_for_trigger(reply, trigger_command=TriggerCommand.RERUN_ANALYSIS)

    assert rendered.startswith("以下是基于最新信息的更新分析：")


def test_reply_renderer_adds_follow_up_prefix_for_summarize_thread() -> None:
    renderer = ReplyRenderer()
    reply = StructuredSummary(
        status=AnalysisResultStatus.SUCCESS,
        confidence=ConfidenceLevel.MEDIUM,
        current_assessment="当前结论已较前一轮更清晰。",
        known_facts=["回滚后错误率下降"],
        impact_scope="当前主要影响支付请求。",
        next_actions=["继续补充日志"],
        citations=[],
        missing_information=[],
    )

    rendered = renderer.render_for_trigger(reply, trigger_command=TriggerCommand.SUMMARIZE_THREAD)

    assert rendered.startswith("以下是基于当前线程的更新总结：")
