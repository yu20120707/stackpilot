from datetime import datetime, timezone
from pathlib import Path

from app.models.contracts import (
    ActionScope,
    ExternalTaskDraft,
    ExternalTaskSyncRequest,
    ExternalTaskTarget,
    PendingActionStatus,
    PendingActionType,
    PendingIncidentAction,
)
from app.services.kernel.action_queue_service import ActionQueueService


def build_task_action(action_id: str, *, status: PendingActionStatus = PendingActionStatus.PENDING_APPROVAL) -> PendingIncidentAction:
    now = datetime.now(timezone.utc)
    return PendingIncidentAction(
        action_id=action_id,
        action_type=PendingActionType.TASK_SYNC,
        status=status,
        title="同步待办草稿",
        preview="将同步 1 个待办草稿。",
        source_thread_id="omt_xxx",
        created_by="ou_alice",
        created_at=now,
        updated_at=now,
        task_sync_request=ExternalTaskSyncRequest(
            target=ExternalTaskTarget.GENERIC,
            source_thread_id="omt_xxx",
            requested_by="ou_alice",
            task_drafts=[
                ExternalTaskDraft(
                    title="Confirm final error rate",
                    description="Source thread: omt_xxx",
                )
            ],
        ),
    )


def test_action_queue_service_replaces_pending_actions_of_same_type(tmp_path: Path) -> None:
    service = ActionQueueService(tmp_path / "actions")
    scope = ActionScope(tenant_id="oc_xxx", thread_id="omt_xxx")

    persisted = service.enqueue_actions(scope, [build_task_action("A1")])
    assert [action.action_id for action in persisted] == ["A1"]

    service.enqueue_actions(scope, [build_task_action("A2")])
    pending_actions = service.list_pending_actions(scope)

    assert [action.action_id for action in pending_actions] == ["A2"]


def test_action_queue_service_updates_and_removes_actions(tmp_path: Path) -> None:
    service = ActionQueueService(tmp_path / "actions")
    scope = ActionScope(tenant_id="oc_xxx", thread_id="omt_xxx")
    persisted_action = build_task_action("A1")
    service.enqueue_actions(scope, [persisted_action])

    updated_action = persisted_action.model_copy(
        update={
            "status": PendingActionStatus.EXECUTED,
            "execution_message": "external_task_sync_succeeded:1",
            "updated_at": datetime.now(timezone.utc),
        }
    )
    service.update_action(scope, updated_action)

    found_action = service.find_action(scope, "a1")
    assert found_action is not None
    assert found_action.status is PendingActionStatus.EXECUTED
    assert found_action.execution_message == "external_task_sync_succeeded:1"

    service.remove_actions(scope, ["A1"])
    assert service.find_action(scope, "A1") is None
