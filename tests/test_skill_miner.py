from datetime import datetime, timezone
from pathlib import Path

from app.models.contracts import (
    ActionScope,
    InteractionEventType,
    InteractionRecord,
    PendingActionType,
    ReviewFeedbackStatus,
    TriggerCommand,
)
from app.services.kernel.audit_log_service import AuditLogService
from app.services.kernel.interaction_recorder import InteractionRecorder
from app.services.skill_miner import SkillMiner
from app.services.skill_registry import SkillRegistry


def build_action_record(event_id: str, correlation_key: str) -> InteractionRecord:
    return InteractionRecord(
        event_id=event_id,
        correlation_key=correlation_key,
        event_type=InteractionEventType.ACTION_EXECUTED,
        tenant_id="oc_xxx",
        thread_id="omt_xxx",
        actor_id="ou_reviewer",
        occurred_at=datetime.now(timezone.utc),
        trigger_command=TriggerCommand.APPROVE_ACTION,
        action_id="A1",
        action_type=PendingActionType.TASK_SYNC,
        pattern_key="incident/task_sync/approval_loop",
        payload={
            "execution_status": "executed",
            "execution_message": "external_task_sync_succeeded:1",
        },
    )


def build_review_feedback_record(event_id: str, correlation_key: str, *, finding_id: str) -> InteractionRecord:
    return InteractionRecord(
        event_id=event_id,
        correlation_key=correlation_key,
        event_type=InteractionEventType.REVIEW_FEEDBACK_RECORDED,
        tenant_id="oc_xxx",
        thread_id="omt_review",
        actor_id="ou_reviewer",
        occurred_at=datetime.now(timezone.utc),
        trigger_command=TriggerCommand.REVIEW_FEEDBACK,
        pattern_key="review/focus/security/accepted_finding",
        payload={
            "finding_id": finding_id,
            "finding_title": "Missing auth guard",
            "focus_areas": ["security"],
            "feedback_status": ReviewFeedbackStatus.ACCEPTED.value,
            "source_ref": "https://github.com/openai/demo/pull/12",
        },
    )


def test_skill_miner_creates_draft_candidate_after_repeated_successes(tmp_path: Path) -> None:
    audit_log_service = AuditLogService(tmp_path / "records")
    recorder = InteractionRecorder(
        tmp_path / "records",
        audit_log_service=audit_log_service,
    )
    registry = SkillRegistry(
        tmp_path / "skills",
        audit_log_service=audit_log_service,
    )
    miner = SkillMiner(
        interaction_recorder=recorder,
        skill_registry=registry,
    )
    scope = ActionScope(tenant_id="oc_xxx", thread_id="omt_xxx")

    recorder.record(scope, build_action_record("evt-1", "action:om_approve_1:A1"))
    assert miner.evaluate_tenant("oc_xxx") == []

    recorder.record(scope, build_action_record("evt-2", "action:om_approve_2:A1"))
    candidates = miner.evaluate_tenant("oc_xxx")

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.status.value == "draft"
    assert candidate.candidate_id == "skill-incident-task-sync-approval"
    assert (tmp_path / "skills" / "oc_xxx" / candidate.candidate_id / "SKILL.md").exists()


def test_skill_miner_creates_review_focus_candidate_after_repeated_acceptance(tmp_path: Path) -> None:
    audit_log_service = AuditLogService(tmp_path / "records")
    recorder = InteractionRecorder(
        tmp_path / "records",
        audit_log_service=audit_log_service,
    )
    registry = SkillRegistry(
        tmp_path / "skills",
        audit_log_service=audit_log_service,
    )
    miner = SkillMiner(
        interaction_recorder=recorder,
        skill_registry=registry,
    )
    first_scope = ActionScope(tenant_id="oc_xxx", thread_id="omt_review_1")
    second_scope = ActionScope(tenant_id="oc_xxx", thread_id="omt_review_2")

    recorder.record(first_scope, build_review_feedback_record("evt-r1", "review-feedback:F1", finding_id="F1"))
    assert miner.evaluate_tenant("oc_xxx") == []

    recorder.record(second_scope, build_review_feedback_record("evt-r2", "review-feedback:F2", finding_id="F2"))
    candidates = miner.evaluate_tenant("oc_xxx")

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.status.value == "draft"
    assert candidate.candidate_id == "skill-review-security-focus"
