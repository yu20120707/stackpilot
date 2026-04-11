from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.models.contracts import (
    AnalysisRequest,
    AnalysisResultRecord,
    AnalysisResultStatus,
    CodeReviewDraft,
    CodeReviewRequest,
    ConfidenceLevel,
    DiffFileChange,
    DiffHunk,
    ExternalTaskSyncRequest,
    ExternalTaskTarget,
    ExternalTaskDraft,
    PostmortemDraft,
    PostmortemStatus,
    PostmortemTimelineEntry,
    ReviewRiskLevel,
    ReviewSourceType,
    StructuredSummary,
    TodoDraftItem,
    ThreadMessage,
    TriggerCommand,
)


def build_thread_message() -> ThreadMessage:
    return ThreadMessage(
        message_id="om_1",
        sender_name="AlertBot",
        sent_at=datetime.now(timezone.utc),
        text="payment service 5xx spike",
    )


def test_analysis_request_accepts_minimum_valid_shape() -> None:
    request = AnalysisRequest(
        trigger_command=TriggerCommand.ANALYZE_INCIDENT,
        chat_id="oc_xxx",
        thread_id="omt_xxx",
        trigger_message_id="om_xxx",
        user_id="ou_xxx",
        user_display_name="Alice",
        thread_messages=[build_thread_message()],
    )

    assert request.trigger_command is TriggerCommand.ANALYZE_INCIDENT
    assert len(request.thread_messages) == 1


def test_thread_message_rejects_blank_text() -> None:
    with pytest.raises(ValidationError):
        ThreadMessage(
            message_id="om_2",
            sender_name="Alice",
            sent_at=datetime.now(timezone.utc),
            text="   ",
        )


def test_result_record_wraps_structured_summary() -> None:
    summary = StructuredSummary(
        status=AnalysisResultStatus.SUCCESS,
        confidence=ConfidenceLevel.MEDIUM,
        current_assessment="Rollback appears to be reducing the error rate.",
        known_facts=["5xx alerts were reported in the payment service."],
        impact_scope="The exact user impact is still unknown.",
        next_actions=["Confirm the last deployment and collect logs."],
        citations=[],
        missing_information=["Error logs"],
    )

    record = AnalysisResultRecord(
        request_id="req_20260410_0001",
        trigger_command=TriggerCommand.ANALYZE_INCIDENT,
        chat_id="oc_xxx",
        thread_id="omt_xxx",
        result_status=AnalysisResultStatus.SUCCESS,
        summary=summary,
    )

    assert record.summary.current_assessment == summary.current_assessment


def test_structured_summary_accepts_conclusion_summary_and_todo_draft() -> None:
    summary = StructuredSummary(
        status=AnalysisResultStatus.SUCCESS,
        confidence=ConfidenceLevel.MEDIUM,
        current_assessment="Rollback is stabilizing the service.",
        known_facts=["The rollback already happened."],
        impact_scope="Payment-related requests were affected.",
        next_actions=["Confirm the error-rate trend."],
        citations=[],
        missing_information=["Full error logs"],
        conclusion_summary="The thread has converged on a rollback-related incident hypothesis.",
        todo_draft=[
            TodoDraftItem(
                title="Confirm the error-rate trend",
                owner_hint="TBD",
                rationale="The thread still lacks final validation.",
            )
        ],
    )

    assert summary.conclusion_summary is not None
    assert summary.todo_draft[0].title == "Confirm the error-rate trend"


def test_external_task_sync_request_accepts_prepared_drafts() -> None:
    request = ExternalTaskSyncRequest(
        target=ExternalTaskTarget.JIRA,
        source_thread_id="omt_xxx",
        requested_by="ou_xxx",
        task_drafts=[
            ExternalTaskDraft(
                title="Collect error logs",
                description="Source thread: omt_xxx\nTask draft: Collect error logs",
            )
        ],
        confirmed=False,
    )

    assert request.target is ExternalTaskTarget.JIRA
    assert request.task_drafts[0].title == "Collect error logs"


def test_postmortem_draft_accepts_reviewable_shape() -> None:
    draft = PostmortemDraft(
        status=PostmortemStatus.DRAFT,
        title="Payment release regression after retry middleware change",
        incident_summary="The discussion converged on a release-related incident.",
        impact_summary="Payment requests were affected during the incident window.",
        timeline=[
            PostmortemTimelineEntry(
                timestamp_hint="2026-04-10T01:00:00+08:00",
                event="Alerting reported a payment service 5xx spike after release.",
            )
        ],
        root_cause_hypothesis="The strongest hypothesis is a release regression.",
        resolution_summary="Rollback stabilized the service pending more evidence.",
        follow_up_actions=["Confirm the final error-rate trend."],
        open_questions=["What was the exact user-impact window?"],
        citations=[],
    )

    assert draft.status is PostmortemStatus.DRAFT
    assert draft.timeline[0].event.startswith("Alerting")


def test_code_review_request_accepts_normalized_diff_shape() -> None:
    request = CodeReviewRequest(
        trigger_command=TriggerCommand.REVIEW_CODE,
        chat_id="oc_xxx",
        thread_id="omt_xxx",
        trigger_message_id="om_xxx",
        user_id="ou_xxx",
        source_type=ReviewSourceType.PATCH_TEXT,
        source_ref="inline_patch",
        raw_input="diff --git a/app/services/tickets.py b/app/services/tickets.py",
        normalized_patch="diff --git a/app/services/tickets.py b/app/services/tickets.py",
        files=[
            DiffFileChange(
                file_path="app/services/tickets.py",
                change_type="modified",
                additions=2,
                deletions=0,
                hunks=[
                    DiffHunk(
                        header="@@ -10,2 +10,4 @@",
                        snippet="+ title = payload.get('title').strip()",
                    )
                ],
            )
        ],
        source_message_text="@stackpilot 审一下这个 diff",
    )

    assert request.trigger_command is TriggerCommand.REVIEW_CODE
    assert request.files[0].file_path == "app/services/tickets.py"


def test_code_review_draft_accepts_structured_findings() -> None:
    draft = CodeReviewDraft(
        status="success",
        overall_assessment="One input-validation path still looks unsafe.",
        overall_risk=ReviewRiskLevel.MEDIUM,
        findings=[],
        missing_context=["No related tests in the diff."],
        publish_recommendation="Keep as draft before publishing.",
    )

    assert draft.status.value == "success"
    assert draft.overall_risk is ReviewRiskLevel.MEDIUM
