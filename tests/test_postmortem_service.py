import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.models.contracts import (
    AnalysisRequest,
    AnalysisResultStatus,
    ConfidenceLevel,
    KnowledgeCitation,
    PostmortemStatus,
    SourceType,
    StructuredSummary,
    ThreadMessage,
    TodoDraftItem,
    TriggerCommand,
)
from app.services.postmortem_service import PostmortemService


FIXTURES_DIR = Path(__file__).parent / "fixtures" / "analysis"


def build_request() -> AnalysisRequest:
    return AnalysisRequest(
        trigger_command=TriggerCommand.SUMMARIZE_THREAD,
        chat_id="oc_xxx",
        thread_id="omt_xxx",
        trigger_message_id="om_trigger",
        user_id="ou_xxx",
        user_display_name="Alice",
        thread_messages=[
            ThreadMessage(
                message_id="om_1",
                sender_name="AlertBot",
                sent_at=datetime(2026, 4, 10, 1, 0, tzinfo=timezone.utc),
                text="payment service 5xx spike after release",
            ),
            ThreadMessage(
                message_id="om_2",
                sender_name="Alice",
                sent_at=datetime(2026, 4, 10, 1, 5, tzinfo=timezone.utc),
                text="we rolled back payment-api",
            ),
            ThreadMessage(
                message_id="om_3",
                sender_name="Bob",
                sent_at=datetime(2026, 4, 10, 1, 12, tzinfo=timezone.utc),
                text="error rate is dropping after rollback",
            ),
        ],
    )


def build_summary() -> StructuredSummary:
    return StructuredSummary(
        status=AnalysisResultStatus.SUCCESS,
        confidence=ConfidenceLevel.MEDIUM,
        current_assessment="The thread points to a release-related payment incident that improved after rollback.",
        known_facts=[
            "The payment service hit 5xx after release.",
            "The team rolled back the payment-api release.",
        ],
        impact_scope="Payment requests were affected during the spike window.",
        next_actions=[
            "Confirm the final post-rollback error-rate trend.",
            "Collect release diff and error-log evidence.",
        ],
        citations=[
            KnowledgeCitation(
                source_type=SourceType.KNOWLEDGE_DOC,
                label="Payment Release 2026-04-10",
                source_uri="https://kb.example.local/releases/payment-2026-04-10",
                snippet="The payment-api release touched retry middleware and idempotency handling.",
            )
        ],
        missing_information=["Detailed error logs", "Exact user-impact window"],
        conclusion_summary="The discussion converged on a release-related issue that improved after rollback.",
        todo_draft=[
            TodoDraftItem(
                title="Confirm the final post-rollback error-rate trend.",
                owner_hint="待确认",
                rationale="The rollback effect still needs final validation.",
            )
        ],
    )


class FakeLLMClient:
    def __init__(self, response: str | Exception) -> None:
        self.response = response
        self.calls: list[tuple[str, str]] = []

    async def generate_structured_summary(self, *, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def load_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


@pytest.mark.anyio
async def test_postmortem_service_returns_llm_draft_on_happy_path(tmp_path: Path) -> None:
    prompt_path = tmp_path / "postmortem_prompt.md"
    prompt_path.write_text("Return structured JSON only.", encoding="utf-8")
    llm_client = FakeLLMClient(load_fixture("postmortem_draft_success.json"))
    service = PostmortemService(llm_client, prompt_path=prompt_path)

    draft = await service.generate_draft(
        request=build_request(),
        summary=build_summary(),
    )

    assert draft.status is PostmortemStatus.DRAFT
    assert "retry middleware" in draft.root_cause_hypothesis
    assert draft.citations == build_summary().citations
    assert len(draft.timeline) == 3
    assert llm_client.calls
    assert "structured_summary" in llm_client.calls[0][1]
    assert "todo_draft" in llm_client.calls[0][1]
    assert "references" in llm_client.calls[0][1]


@pytest.mark.anyio
async def test_postmortem_service_falls_back_to_summary_backed_draft_for_invalid_json(
    tmp_path: Path,
) -> None:
    prompt_path = tmp_path / "postmortem_prompt.md"
    prompt_path.write_text("Return structured JSON only.", encoding="utf-8")
    llm_client = FakeLLMClient("{invalid json")
    service = PostmortemService(llm_client, prompt_path=prompt_path)

    draft = await service.generate_draft(
        request=build_request(),
        summary=build_summary(),
    )

    assert draft.status is PostmortemStatus.DRAFT
    assert draft.title
    assert draft.incident_summary == build_summary().current_assessment
    assert draft.follow_up_actions == [item.title for item in build_summary().todo_draft]
    assert draft.open_questions == build_summary().missing_information
    assert draft.citations == build_summary().citations
