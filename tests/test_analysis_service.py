import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.clients.llm_client import LLMClientError
from app.models.contracts import (
    AnalysisResultStatus,
    ConfidenceLevel,
    AnalysisRequest,
    KnowledgeCitation,
    SourceType,
    ThreadMessage,
    TriggerCommand,
)
from app.services.incident.analysis_service import AnalysisService


FIXTURES_DIR = Path(__file__).parent / "fixtures" / "analysis"


def build_request(*messages: str) -> AnalysisRequest:
    return AnalysisRequest(
        trigger_command=TriggerCommand.ANALYZE_INCIDENT,
        chat_id="oc_xxx",
        thread_id="omt_xxx",
        trigger_message_id="om_trigger",
        user_id="ou_xxx",
        user_display_name="Alice",
        thread_messages=[
            ThreadMessage(
                message_id=f"om_{index}",
                sender_name="Alice",
                sent_at=datetime.now(timezone.utc),
                text=text,
            )
            for index, text in enumerate(messages, start=1)
        ],
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


class FakeLLMClient:
    def __init__(self, response: str | Exception) -> None:
        self.response = response
        self.calls: list[tuple[str, str]] = []

    async def generate_structured_summary(self, *, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def load_summary_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


@pytest.mark.anyio
async def test_analysis_service_returns_structured_summary_on_happy_path(tmp_path: Path) -> None:
    prompt_path = tmp_path / "analysis_prompt.md"
    prompt_path.write_text("Return structured JSON only.", encoding="utf-8")
    llm_client = FakeLLMClient(load_summary_fixture("structured_summary_success.json"))
    service = AnalysisService(llm_client, prompt_path=prompt_path)

    result = await service.summarize(
        build_request(
            "payment service 5xx spike after deployment",
            "we rolled back payment-api and the error rate is dropping",
        ),
        citations=build_citations(),
    )

    assert result.status == AnalysisResultStatus.SUCCESS
    assert result.confidence == ConfidenceLevel.MEDIUM
    assert result.citations == build_citations()
    assert len(llm_client.calls) == 1
    assert "thread_context" in llm_client.calls[0][1]
    assert "references" in llm_client.calls[0][1]


@pytest.mark.anyio
async def test_analysis_service_returns_insufficient_context_without_llm_call(tmp_path: Path) -> None:
    prompt_path = tmp_path / "analysis_prompt.md"
    prompt_path.write_text("Return structured JSON only.", encoding="utf-8")
    llm_client = FakeLLMClient(load_summary_fixture("structured_summary_success.json"))
    service = AnalysisService(llm_client, prompt_path=prompt_path)

    result = await service.summarize(
        build_request("服务异常了，帮忙看看"),
        citations=[],
    )

    assert result.status == AnalysisResultStatus.INSUFFICIENT_CONTEXT
    assert result.confidence == ConfidenceLevel.LOW
    assert result.missing_information
    assert llm_client.calls == []


@pytest.mark.anyio
async def test_analysis_service_keeps_insufficient_context_when_weak_evidence_is_filtered(
    tmp_path: Path,
) -> None:
    prompt_path = tmp_path / "analysis_prompt.md"
    prompt_path.write_text("Return structured JSON only.", encoding="utf-8")
    llm_client = FakeLLMClient(load_summary_fixture("structured_summary_success.json"))
    service = AnalysisService(llm_client, prompt_path=prompt_path)

    result = await service.summarize(
        build_request("payment looks odd", "please help"),
        citations=[],
    )

    assert result.status == AnalysisResultStatus.INSUFFICIENT_CONTEXT
    assert llm_client.calls == []


@pytest.mark.anyio
async def test_analysis_service_returns_temporary_failure_for_invalid_json(tmp_path: Path) -> None:
    prompt_path = tmp_path / "analysis_prompt.md"
    prompt_path.write_text("Return structured JSON only.", encoding="utf-8")
    llm_client = FakeLLMClient("{invalid json")
    service = AnalysisService(llm_client, prompt_path=prompt_path)

    result = await service.summarize(
        build_request(
            "payment service 5xx spike after deployment",
            "please confirm release and inspect logs",
        ),
        citations=build_citations(),
    )

    assert result.status == AnalysisResultStatus.TEMPORARY_FAILURE
    assert result.retry_hint == "请稍后重试，或补充更多上下文后再次触发。"


@pytest.mark.anyio
async def test_analysis_service_returns_temporary_failure_for_llm_error(tmp_path: Path) -> None:
    prompt_path = tmp_path / "analysis_prompt.md"
    prompt_path.write_text("Return structured JSON only.", encoding="utf-8")
    llm_client = FakeLLMClient(LLMClientError("request failed"))
    service = AnalysisService(llm_client, prompt_path=prompt_path)

    result = await service.summarize(
        build_request(
            "payment service 5xx spike after deployment",
            "please confirm release and inspect logs",
        ),
        citations=build_citations(),
    )

    assert result.status == AnalysisResultStatus.TEMPORARY_FAILURE
    assert result.citations == build_citations()


@pytest.mark.anyio
async def test_analysis_service_adds_conclusion_summary_and_todo_draft_for_summarize_thread(
    tmp_path: Path,
) -> None:
    prompt_path = tmp_path / "analysis_prompt.md"
    prompt_path.write_text("Return structured JSON only.", encoding="utf-8")
    llm_client = FakeLLMClient(
        json.dumps(
            {
                "status": "success",
                "confidence": "medium",
                "current_assessment": "The thread points to a deployment-related payment issue that is stabilizing after rollback.",
                "known_facts": [
                    "The payment service hit 5xx after deployment.",
                    "A rollback was executed.",
                ],
                "impact_scope": "Payment requests were impacted during the spike.",
                "next_actions": [
                    "Confirm the post-rollback error trend.",
                    "Collect deployment and log evidence.",
                ],
                "citations": [],
                "missing_information": ["Detailed error logs"],
            }
        )
    )
    service = AnalysisService(llm_client, prompt_path=prompt_path)
    request = build_request(
        "payment service 5xx spike after deployment",
        "we rolled back payment-api and the error rate is dropping",
    ).model_copy(update={"trigger_command": TriggerCommand.SUMMARIZE_THREAD})

    result = await service.summarize(request, citations=build_citations())

    assert result.status == AnalysisResultStatus.SUCCESS
    assert result.conclusion_summary is not None
    assert "stabilizing" in result.conclusion_summary
    assert result.todo_draft
    assert result.todo_draft[0].title == "Confirm the post-rollback error trend."
    assert result.todo_draft[0].owner_hint == "待确认"
    assert len(llm_client.calls) == 1
    assert "closing_summary_requirements" in llm_client.calls[0][1]
    assert "conclusion_summary" in llm_client.calls[0][1]
    assert "todo_draft" in llm_client.calls[0][1]


def test_analysis_service_normalizes_common_status_and_citation_shapes(tmp_path: Path) -> None:
    prompt_path = tmp_path / "analysis_prompt.md"
    prompt_path.write_text("Return structured JSON only.", encoding="utf-8")
    service = AnalysisService(FakeLLMClient("{}"), prompt_path=prompt_path)

    summary = service._parse_summary_response(
        json.dumps(
            {
                "status": "mitigation_in_progress",
                "confidence": "medium",
                "current_assessment": "Rollback is stabilizing the service.",
                "known_facts": ["The payment service hit 5xx after release."],
                "impact_scope": "Payment requests were affected during the incident window.",
                "next_actions": ["Confirm the final post-rollback trend."],
                "citations": [
                    "thread:AlertBot@2026-04-10T01:00:00Z",
                    "data/knowledge/payment-sop.md",
                ],
                "missing_information": ["Detailed error logs"],
            }
        )
    )

    assert summary.status == AnalysisResultStatus.SUCCESS
    assert summary.citations[0].source_type == SourceType.THREAD_MESSAGE
    assert summary.citations[1].source_type == SourceType.KNOWLEDGE_DOC


def test_analysis_service_normalizes_list_impact_scope_and_short_source_type_aliases(
    tmp_path: Path,
) -> None:
    prompt_path = tmp_path / "analysis_prompt.md"
    prompt_path.write_text("Return structured JSON only.", encoding="utf-8")
    service = AnalysisService(FakeLLMClient("{}"), prompt_path=prompt_path)

    summary = service._parse_summary_response(
        json.dumps(
            {
                "status": "success",
                "confidence": "medium",
                "current_assessment": "Rollback is stabilizing the service.",
                "known_facts": ["The payment service hit 5xx after release."],
                "impact_scope": [
                    "Checkout failures were reported.",
                    "Exact volume is still unknown.",
                ],
                "next_actions": ["Confirm the final post-rollback trend."],
                "citations": [
                    {
                        "source_type": "thread",
                        "label": "AlertBot",
                        "source_uri": "thread://incident/1",
                        "snippet": "payment service 5xx spike",
                    },
                    {
                        "source_type": "doc",
                        "label": "Payment Service SOP",
                        "source_uri": "data/knowledge/payment-sop.md",
                        "snippet": "confirm release scope and logs",
                    },
                ],
                "missing_information": ["Detailed error logs"],
            }
        )
    )

    assert summary.impact_scope == "Checkout failures were reported. Exact volume is still unknown."
    assert summary.citations[0].source_type == SourceType.THREAD_MESSAGE
    assert summary.citations[1].source_type == SourceType.KNOWLEDGE_DOC
