from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.models.contracts import SkillCandidate, SkillCandidateStatus
from app.services.kernel.audit_log_service import AuditLogService
from app.services.growth.skill_registry import SkillRegistry


def build_candidate() -> SkillCandidate:
    now = datetime.now(timezone.utc)
    return SkillCandidate(
        candidate_id="skill-incident-task-sync-approval",
        tenant_id="oc_xxx",
        name="incident-task-sync-approval-loop",
        workflow="incident",
        status=SkillCandidateStatus.DRAFT,
        source_pattern_key="incident/task_sync/approval_loop",
        trigger_conditions=["A summarize-thread run produced pending task-sync actions."],
        steps=["Wait for approval."],
        verification_steps=["The action status becomes executed."],
        failure_signals=["external_task_sync_failed"],
        evidence_event_ids=["evt-1", "evt-2"],
        created_at=now,
        updated_at=now,
    )


def test_skill_registry_requires_approval_before_activation(tmp_path: Path) -> None:
    audit_log_service = AuditLogService(tmp_path / "records")
    registry = SkillRegistry(
        tmp_path / "skills",
        audit_log_service=audit_log_service,
    )
    candidate = registry.create_draft_candidate(build_candidate())

    with pytest.raises(ValueError):
        registry.activate_candidate(candidate.tenant_id, candidate.candidate_id, "ou_reviewer")

    approved = registry.approve_candidate(candidate.tenant_id, candidate.candidate_id, "ou_reviewer")
    activated = registry.activate_candidate(candidate.tenant_id, candidate.candidate_id, "ou_reviewer")

    assert approved.status is SkillCandidateStatus.APPROVED
    assert activated.status is SkillCandidateStatus.ACTIVE
    assert (tmp_path / "skills" / "oc_xxx" / candidate.candidate_id / "SKILL.md").exists()
    assert [entry.event_type for entry in audit_log_service.list_entries("oc_xxx")] == [
        "candidate_created",
        "candidate_approved",
        "candidate_activated",
    ]


def test_skill_registry_lists_candidates(tmp_path: Path) -> None:
    registry = SkillRegistry(tmp_path / "skills")
    registry.create_draft_candidate(build_candidate())

    candidates = registry.list_candidates("oc_xxx")

    assert len(candidates) == 1
    assert candidates[0].candidate_id == "skill-incident-task-sync-approval"
