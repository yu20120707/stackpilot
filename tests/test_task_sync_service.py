import pytest

from app.models.contracts import (
    AnalysisResultStatus,
    ConfidenceLevel,
    ExternalTaskTarget,
    KnowledgeCitation,
    SourceType,
    StructuredSummary,
    TaskSyncStatus,
    TodoDraftItem,
)
from app.services.incident.task_sync_service import TaskSyncService


def build_summary() -> StructuredSummary:
    return StructuredSummary(
        status=AnalysisResultStatus.SUCCESS,
        confidence=ConfidenceLevel.MEDIUM,
        current_assessment="Rollback is stabilizing the payment service after the release-related spike.",
        known_facts=[
            "The payment service hit 5xx after release.",
            "The team already rolled back the change.",
        ],
        impact_scope="Payment-related requests were affected during the spike window.",
        next_actions=[
            "Confirm the final error-rate trend.",
            "Collect deployment and error-log evidence.",
        ],
        citations=[
            KnowledgeCitation(
                source_type=SourceType.KNOWLEDGE_DOC,
                label="Payment Release 2026-04-10",
                source_uri="https://kb.example.local/releases/payment-2026-04-10",
                snippet="The payment-api release touched retry middleware and idempotency handling.",
            )
        ],
        missing_information=["Detailed error logs"],
        conclusion_summary="The thread has largely converged on a release-related issue that improved after rollback.",
        todo_draft=[
            TodoDraftItem(
                title="Confirm the final error-rate trend.",
                owner_hint="待确认",
                rationale="The rollback effect still needs a final stability check.",
            )
        ],
    )


class FakeTaskSyncClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def create_task(self, *, target, draft):  # noqa: ANN001
        self.calls.append((target.value, draft.title))
        return {
            "title": draft.title,
            "external_id": f"TASK-{len(self.calls)}",
            "external_url": f"https://tasks.example.local/{len(self.calls)}",
        }


def test_task_sync_service_builds_sync_request_from_summary() -> None:
    service = TaskSyncService()

    request = service.build_sync_request_from_summary(
        build_summary(),
        source_thread_id="omt_payment",
        requested_by="ou_alice",
        target=ExternalTaskTarget.JIRA,
    )

    assert request.target is ExternalTaskTarget.JIRA
    assert request.source_thread_id == "omt_payment"
    assert request.require_confirmation is True
    assert request.confirmed is False
    assert len(request.task_drafts) == 1
    assert request.task_drafts[0].title == "Confirm the final error-rate trend."
    assert "Conclusion summary:" in request.task_drafts[0].description
    assert request.task_drafts[0].citations[0].label == "Payment Release 2026-04-10"


@pytest.mark.anyio
async def test_task_sync_service_requires_confirmation_before_sync() -> None:
    service = TaskSyncService(task_sync_client=FakeTaskSyncClient())
    request = service.build_sync_request_from_summary(
        build_summary(),
        source_thread_id="omt_payment",
        requested_by="ou_alice",
    )

    result = await service.sync_prepared_tasks(request)

    assert result.status is TaskSyncStatus.REQUIRES_CONFIRMATION
    assert result.synced_tasks == []
    assert result.prepared_drafts
    assert result.message == "external_task_sync_requires_confirmation"


@pytest.mark.anyio
async def test_task_sync_service_syncs_confirmed_drafts() -> None:
    fake_client = FakeTaskSyncClient()
    service = TaskSyncService(task_sync_client=fake_client)
    request = service.build_sync_request_from_summary(
        build_summary(),
        source_thread_id="omt_payment",
        requested_by="ou_alice",
        confirmed=True,
    )

    result = await service.sync_prepared_tasks(request)

    assert result.status is TaskSyncStatus.SYNCED
    assert len(result.synced_tasks) == 1
    assert result.synced_tasks[0].external_id == "TASK-1"
    assert fake_client.calls == [("generic", "Confirm the final error-rate trend.")]
