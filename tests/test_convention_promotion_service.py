from datetime import datetime, timezone
from pathlib import Path

from app.models.contracts import ActionScope, SkillCandidate, SkillCandidateStatus
from app.services.growth.convention_promotion_service import ConventionPromotionService
from app.services.kernel.audit_log_service import AuditLogService
from app.services.kernel.action_queue_service import ActionQueueService
from app.services.kernel.canonical_convention_service import CanonicalConventionService
from app.services.growth.skill_registry import SkillRegistry


def build_candidate(
    *,
    status: SkillCandidateStatus = SkillCandidateStatus.DRAFT,
) -> SkillCandidate:
    now = datetime.now(timezone.utc)
    return SkillCandidate(
        candidate_id="skill-review-security-focus",
        tenant_id="oc_xxx",
        name="review-security-focus-loop",
        workflow="review",
        status=status,
        source_pattern_key="review/focus/security/accepted_finding",
        trigger_conditions=["Users repeatedly accepted security findings."],
        steps=["Resolve security focus.", "Generate review findings."],
        verification_steps=["Accepted findings remain traceable."],
        failure_signals=["Repeated ignored findings."],
        evidence_event_ids=["evt-1", "evt-2"],
        created_at=now,
        updated_at=now,
    )


def test_convention_promotion_service_writes_versioned_canonical_docs_and_activates_candidate(
    tmp_path: Path,
) -> None:
    audit_log_service = AuditLogService(tmp_path / "records")
    skill_registry = SkillRegistry(tmp_path / "skills", audit_log_service=audit_log_service)
    candidate = skill_registry.create_draft_candidate(build_candidate())
    skill_registry.approve_candidate(candidate.tenant_id, candidate.candidate_id, "ou_reviewer")
    action_queue_service = ActionQueueService(tmp_path / "actions")
    canonical_service = CanonicalConventionService(
        tmp_path / "knowledge",
        audit_log_service=audit_log_service,
    )
    service = ConventionPromotionService(
        action_queue_service=action_queue_service,
        skill_registry=skill_registry,
        canonical_convention_service=canonical_service,
    )
    scope = ActionScope(tenant_id="oc_xxx", thread_id="omt_xxx")

    first_action = service.prepare_promotion_action(
        scope=scope,
        candidate_id=candidate.candidate_id,
        requested_by="ou_alice",
    )
    service.persist_actions(scope=scope, actions=[first_action])
    executed_action, _ = service.execute_promotion_action(
        scope=scope,
        action_id=first_action.action_id,
        approved_by="ou_reviewer",
    )

    assert executed_action is not None
    assert (tmp_path / "knowledge" / "canonical" / "oc_xxx" / "skill-review-security-focus.v1.canonical.json").exists()
    activated = skill_registry.load_candidate("oc_xxx", candidate.candidate_id)
    assert activated is not None
    assert activated.status is SkillCandidateStatus.ACTIVE

    second_action = service.prepare_promotion_action(
        scope=scope,
        candidate_id=candidate.candidate_id,
        requested_by="ou_alice",
    )
    service.persist_actions(scope=scope, actions=[second_action])
    service.execute_promotion_action(
        scope=scope,
        action_id=second_action.action_id,
        approved_by="ou_reviewer",
    )

    assert (tmp_path / "knowledge" / "canonical" / "oc_xxx" / "skill-review-security-focus.v1.canonical.json").exists()
    assert (tmp_path / "knowledge" / "canonical" / "oc_xxx" / "skill-review-security-focus.v2.canonical.json").exists()
    assert [entry.event_type for entry in audit_log_service.list_entries("oc_xxx")] == [
        "candidate_created",
        "candidate_approved",
        "candidate_activated",
        "canonical_convention_promoted",
        "canonical_convention_promoted",
    ]
