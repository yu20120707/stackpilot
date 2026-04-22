from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from app.main import app
from app.models.contracts import (
    AnalysisResultStatus,
    AlertIngressResult,
    ConfidenceLevel,
    FeishuReplySendResult,
    FeishuTarget,
    IncidentSeed,
    StructuredSummary,
    TriggerCommand,
)
from app.services.incident.alert_ingress_flow import AlertIngressFlow


class FakeKnowledgeBase:
    def __init__(self) -> None:
        self.requests: list = []

    def retrieve_citations(self, analysis_request):  # noqa: ANN001
        self.requests.append(analysis_request)
        return []


class FakeAnalysisService:
    def __init__(self, reply: StructuredSummary | None = None) -> None:
        self.requests: list[tuple[object, list]] = []
        self.reply = reply or StructuredSummary(
            status=AnalysisResultStatus.SUCCESS,
            confidence=ConfidenceLevel.MEDIUM,
            current_assessment="支付链路出现异常抖动。",
            known_facts=["支付错误率上升"],
            impact_scope="支付下单",
            next_actions=["检查网关", "确认最近发布"],
            citations=[],
            missing_information=[],
        )

    async def summarize(self, request, citations=None):  # noqa: ANN001
        self.requests.append((request, list(citations or [])))
        return self.reply


class FakeReplyRenderer:
    def __init__(self) -> None:
        self.calls: list[tuple[object, object]] = []

    def render_for_trigger(self, reply, trigger_command=None):  # noqa: ANN001
        self.calls.append((reply, trigger_command))
        return "rendered alert reply"


class FakeFeishuClient:
    def __init__(self, result: FeishuReplySendResult | None = None) -> None:
        self.calls: list[dict[str, object]] = []
        self.result = result or FeishuReplySendResult(
            success=True,
            reply_message_id="om_reply_root",
        )

    async def reply_to_thread(self, **kwargs):  # noqa: ANN001
        self.calls.append(kwargs)
        return self.result


class FakeAlertIngressFlow:
    def __init__(self) -> None:
        self.calls: list[object] = []

    async def process_webhook(self, payload) -> AlertIngressResult:  # noqa: ANN001
        self.calls.append(payload)
        return AlertIngressResult(success=True)


def build_flow() -> tuple[AlertIngressFlow, FakeKnowledgeBase, FakeAnalysisService, FakeReplyRenderer, FakeFeishuClient]:
    knowledge_base = FakeKnowledgeBase()
    analysis_service = FakeAnalysisService()
    reply_renderer = FakeReplyRenderer()
    feishu_client = FakeFeishuClient()
    flow = AlertIngressFlow(
        analysis_service=analysis_service,
        knowledge_base=knowledge_base,
        reply_renderer=reply_renderer,
        feishu_client=feishu_client,
    )
    return flow, knowledge_base, analysis_service, reply_renderer, feishu_client


def test_alert_webhook_rejects_invalid_secret(monkeypatch) -> None:
    fake_flow = FakeAlertIngressFlow()
    monkeypatch.setattr(app.state.services, "alert_ingress_flow", fake_flow)
    monkeypatch.setattr(app.state.settings, "alert_webhook_secret", "topsecret")

    client = TestClient(app)
    response = client.post(
        "/api/alerts/events",
        json={"title": "Payment spike"},
        headers={"X-Alert-Webhook-Secret": "wrong-secret"},
    )

    assert response.status_code == 401
    assert fake_flow.calls == []


def test_alert_ingress_normalizes_payload_into_incident_seed() -> None:
    flow, _, _, _, _ = build_flow()

    seed = flow.normalize_incident_seed(
        {
            "title": "Payment spike",
            "source": "payments-api",
            "summary": "Checkout errors increased.",
            "severity": "critical",
            "evidence_lines": [
                "5xx rate > 20%",
                "p95 latency > 2s",
            ],
            "feishu_target": {
                "chat_id": "oc_xxx",
                "thread_id": "omt_xxx",
                "trigger_message_id": "om_root",
            },
        }
    )

    assert seed == IncidentSeed(
        title="Payment spike",
        source="payments-api",
        summary="Checkout errors increased.",
        severity="critical",
        evidence_lines=["5xx rate > 20%", "p95 latency > 2s"],
        feishu_target=FeishuTarget(
            chat_id="oc_xxx",
            thread_id="omt_xxx",
            trigger_message_id="om_root",
        ),
        raw_payload={
            "title": "Payment spike",
            "source": "payments-api",
            "summary": "Checkout errors increased.",
            "severity": "critical",
            "evidence_lines": [
                "5xx rate > 20%",
                "p95 latency > 2s",
            ],
            "feishu_target": {
                "chat_id": "oc_xxx",
                "thread_id": "omt_xxx",
                "trigger_message_id": "om_root",
            },
        },
    )


@pytest.mark.anyio
async def test_alert_ingress_builds_synthetic_analysis_request_and_replies() -> None:
    flow, knowledge_base, analysis_service, reply_renderer, feishu_client = build_flow()

    result = await flow.process_webhook(
        {
            "title": "Payment spike",
            "source": "payments-api",
            "summary": "Checkout errors increased.",
            "severity": "critical",
            "evidence_lines": [
                "5xx rate > 20%",
                "p95 latency > 2s",
            ],
            "feishu_target": {
                "chat_id": "oc_xxx",
                "thread_id": "omt_xxx",
                "trigger_message_id": "om_root",
            },
        }
    )

    assert result.success is True
    assert result.delivered_to_feishu is True
    assert result.reply_message_id == "om_reply_root"

    assert len(knowledge_base.requests) == 1
    assert len(analysis_service.requests) == 1
    analysis_request, citations = analysis_service.requests[0]
    assert citations == []
    assert analysis_request.trigger_command is TriggerCommand.ANALYZE_INCIDENT
    assert analysis_request.chat_id == "oc_xxx"
    assert analysis_request.thread_id == "omt_xxx"
    assert analysis_request.trigger_message_id == "om_root"
    assert [message.text for message in analysis_request.thread_messages] == [
        "Alert: Payment spike\nSource: payments-api\nSeverity: critical\nSummary: Checkout errors increased.",
        "5xx rate > 20%",
        "p95 latency > 2s",
    ]

    assert len(reply_renderer.calls) == 1
    assert reply_renderer.calls[0][1] is TriggerCommand.ANALYZE_INCIDENT
    assert feishu_client.calls == [
        {
            "chat_id": "oc_xxx",
            "thread_id": "omt_xxx",
            "trigger_message_id": "om_root",
            "reply_text": "rendered alert reply",
        }
    ]


@pytest.mark.anyio
async def test_alert_ingress_degrades_without_feishu_anchor() -> None:
    flow, knowledge_base, analysis_service, reply_renderer, feishu_client = build_flow()

    result = await flow.process_webhook(
        {
            "title": "Cache growth",
            "summary": "Redis memory keeps growing.",
            "evidence_lines": ["eviction rate still zero"],
        }
    )

    assert result.success is True
    assert result.delivered_to_feishu is False
    assert result.reply_message_id is None
    assert len(knowledge_base.requests) == 1
    assert len(analysis_service.requests) == 1
    assert len(reply_renderer.calls) == 1
    assert feishu_client.calls == []

    analysis_request, _ = analysis_service.requests[0]
    assert analysis_request.chat_id == "alert-ingress"
    assert analysis_request.thread_id.startswith("alert-thread-")
    assert analysis_request.trigger_message_id.startswith("alert-trigger-")
