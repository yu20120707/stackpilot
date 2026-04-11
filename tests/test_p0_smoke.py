import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.contracts import (
    AnalysisResultStatus,
    FeishuReplySendResult,
    FeishuThreadLoadResponse,
    NormalizedFeishuMessageEvent,
)
from app.services.analysis_service import AnalysisService
from app.services.knowledge_base import KnowledgeBase
from app.services.reply_renderer import ReplyRenderer
from app.services.thread_reader import ThreadReader
from app.clients.feishu_client import FeishuClient


FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def disable_verification_token_check(monkeypatch) -> None:
    monkeypatch.setattr(app.state.settings, "feishu_verification_token", None)


def load_json(*relative_parts: str) -> dict:
    return json.loads((FIXTURES_DIR.joinpath(*relative_parts)).read_text(encoding="utf-8"))


def load_text(*relative_parts: str) -> str:
    return FIXTURES_DIR.joinpath(*relative_parts).read_text(encoding="utf-8")


class FakeThreadFeishuClient(FeishuClient):
    def __init__(self, thread_payload: dict) -> None:
        super().__init__()
        self.thread_payload = thread_payload
        self.fetch_calls: list[tuple[str, str, str]] = []
        self.reply_calls: list[tuple[str, str, str, str]] = []

    async def fetch_thread_messages(
        self,
        *,
        chat_id: str,
        message_id: str,
        thread_id: str,
    ) -> FeishuThreadLoadResponse:
        self.fetch_calls.append((chat_id, message_id, thread_id))
        return FeishuThreadLoadResponse.model_validate(self.thread_payload)

    async def reply_to_thread(
        self,
        *,
        chat_id: str,
        thread_id: str,
        trigger_message_id: str,
        reply_text: str,
    ) -> FeishuReplySendResult:
        self.reply_calls.append((chat_id, thread_id, trigger_message_id, reply_text))
        return FeishuReplySendResult(success=True, reply_message_id="om_reply_smoke")


class FakeLLMClient:
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[tuple[str, str]] = []

    async def generate_structured_summary(self, *, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        return self.response


def accepted_message_event_from_fixture(name: str) -> NormalizedFeishuMessageEvent:
    client = TestClient(app)
    response = client.post("/api/feishu/events", json=load_json("feishu", name))
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["status"] == "accepted"
    return NormalizedFeishuMessageEvent.model_validate(payload["message_event"])


@pytest.mark.anyio
async def test_p0_happy_path_smoke_flow() -> None:
    trigger_event = accepted_message_event_from_fixture("supported_message_event.json")
    feishu_client = FakeThreadFeishuClient(load_json("feishu", "thread_messages.json"))
    thread_reader = ThreadReader(feishu_client)
    request = await thread_reader.build_analysis_request(
        trigger_command="analyze_incident",
        trigger_event=trigger_event,
    )

    knowledge_base = KnowledgeBase(FIXTURES_DIR / "knowledge", max_hits=3)
    citations = knowledge_base.retrieve_citations(request)
    llm_client = FakeLLMClient(load_text("analysis", "structured_summary_success.json"))
    analysis_service = AnalysisService(
        llm_client,
        prompt_path=Path("app/prompts/analysis_prompt.md"),
    )
    summary = await analysis_service.summarize(request, citations=citations)
    rendered_reply = ReplyRenderer().render(summary)
    send_result = await feishu_client.reply_to_thread(
        chat_id=request.chat_id,
        thread_id=request.thread_id,
        trigger_message_id=request.trigger_message_id,
        reply_text=rendered_reply,
    )

    assert request.thread_messages
    assert citations
    assert summary.status == AnalysisResultStatus.SUCCESS
    assert "当前判断：" in rendered_reply
    assert "参考来源：" in rendered_reply
    assert "Payment Service SOP" in rendered_reply
    assert llm_client.calls
    assert send_result.success is True
    assert feishu_client.reply_calls


@pytest.mark.anyio
async def test_p0_insufficient_context_smoke_flow() -> None:
    trigger_event = accepted_message_event_from_fixture("supported_message_event.json")
    feishu_client = FakeThreadFeishuClient(load_json("feishu", "thread_messages_insufficient.json"))
    thread_reader = ThreadReader(feishu_client)
    request = await thread_reader.build_analysis_request(
        trigger_command="analyze_incident",
        trigger_event=trigger_event,
    )

    knowledge_base = KnowledgeBase(FIXTURES_DIR / "analysis" / "missing-dir", max_hits=3)
    citations = knowledge_base.retrieve_citations(request)
    llm_client = FakeLLMClient(load_text("analysis", "structured_summary_success.json"))
    analysis_service = AnalysisService(
        llm_client,
        prompt_path=Path("app/prompts/analysis_prompt.md"),
    )
    summary = await analysis_service.summarize(request, citations=citations)
    rendered_reply = ReplyRenderer().render(summary)

    assert citations == []
    assert summary.status == AnalysisResultStatus.INSUFFICIENT_CONTEXT
    assert "缺少信息：" in rendered_reply
    assert "错误日志" in rendered_reply or "更多可验证的上下文" in rendered_reply
    assert llm_client.calls == []


def test_p0_unsupported_chatter_still_produces_no_accepted_analysis_request() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/feishu/events",
        json=load_json("feishu", "unsupported_message_event.json"),
    )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "ignored"
    assert response.json()["data"]["reason"] == "unsupported_message"
