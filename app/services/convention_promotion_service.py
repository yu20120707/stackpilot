from __future__ import annotations

from datetime import datetime, timezone

from app.models.contracts import (
    ActionScope,
    CanonicalConventionDocument,
    CanonicalConventionPromotionRequest,
    CanonicalConventionStatus,
    CanonicalPolicyDocument,
    CanonicalPolicyScope,
    OrgReviewDefaults,
    PendingActionStatus,
    PendingActionType,
    PendingIncidentAction,
    ReviewFocusArea,
    SkillCandidate,
    SkillCandidateStatus,
)
from app.services.kernel.action_queue_service import ActionQueueService
from app.services.kernel.canonical_convention_service import CanonicalConventionService
from app.services.skill_registry import SkillRegistry


class ConventionPromotionService:
    def __init__(
        self,
        *,
        action_queue_service: ActionQueueService,
        skill_registry: SkillRegistry,
        canonical_convention_service: CanonicalConventionService,
    ) -> None:
        self.action_queue_service = action_queue_service
        self.skill_registry = skill_registry
        self.canonical_convention_service = canonical_convention_service

    def prepare_promotion_action(
        self,
        *,
        scope: ActionScope,
        candidate_id: str,
        requested_by: str,
    ) -> PendingIncidentAction:
        candidate = self._require_promotable_candidate(scope.tenant_id, candidate_id)
        promotion_request = self._build_promotion_request(
            candidate=candidate,
            requested_by=requested_by,
        )
        now = datetime.now(timezone.utc)
        action_id = self.action_queue_service.allocate_action_id(scope)
        return PendingIncidentAction(
            action_id=action_id,
            action_type=PendingActionType.CANONICAL_CONVENTION_PROMOTION,
            status=PendingActionStatus.PENDING_APPROVAL,
            title="推广 canonical 规范",
            preview=(
                f"将 {candidate.name} 推广为 canonical convention "
                f"v{promotion_request.target_version}。"
            ),
            source_thread_id=scope.thread_id,
            created_by=requested_by,
            created_at=now,
            updated_at=now,
            canonical_promotion_request=promotion_request,
        )

    def persist_actions(
        self,
        *,
        scope: ActionScope,
        actions: list[PendingIncidentAction],
    ) -> list[PendingIncidentAction]:
        return self.action_queue_service.enqueue_actions(scope, actions)

    def discard_actions(
        self,
        *,
        scope: ActionScope,
        actions: list[PendingIncidentAction],
    ) -> None:
        self.action_queue_service.remove_actions(
            scope,
            [action.action_id for action in actions],
        )

    def render_pending_actions(self, actions: list[PendingIncidentAction]) -> str:
        if not actions:
            return ""

        lines = ["待审批动作："]
        for action in actions:
            lines.append(f"- [{action.action_id}] {action.title}")
            lines.append(f"  {action.preview}")
            lines.append(f"  批准命令：批准动作 {action.action_id}")
        return "\n".join(lines)

    def can_handle_action(self, scope: ActionScope, action_id: str) -> bool:
        action = self.action_queue_service.find_action(scope, action_id)
        return bool(
            action is not None
            and action.action_type is PendingActionType.CANONICAL_CONVENTION_PROMOTION
        )

    def execute_promotion_action(
        self,
        *,
        scope: ActionScope,
        action_id: str,
        approved_by: str,
    ) -> tuple[PendingIncidentAction | None, str]:
        action = self.action_queue_service.find_action(scope, action_id)
        if action is None:
            return None, f"未找到待审批动作：{action_id.upper()}。请确认动作编号是否来自当前线程。"
        if action.status is not PendingActionStatus.PENDING_APPROVAL:
            suffix = action.execution_message or "already_processed"
            return None, f"动作 {action.action_id} 已处理，无需重复批准。({suffix})"
        if action.action_type is not PendingActionType.CANONICAL_CONVENTION_PROMOTION:
            return None, f"动作 {action.action_id} 不是可执行的 canonical 推广动作。"
        if action.canonical_promotion_request is None:
            return None, f"动作 {action.action_id} 缺少 canonical 推广请求快照。"

        promotion_request = action.canonical_promotion_request
        candidate = self.skill_registry.load_candidate(scope.tenant_id, promotion_request.candidate_id)
        if candidate is not None and candidate.status is SkillCandidateStatus.APPROVED:
            self.skill_registry.activate_candidate(scope.tenant_id, candidate.candidate_id, approved_by)

        written_path = self.canonical_convention_service.write_promoted_document(
            tenant_id=scope.tenant_id,
            document=promotion_request.canonical_document,
            promoted_by=approved_by,
            related_action_id=action.action_id,
        )
        now = datetime.now(timezone.utc)
        updated_action = action.model_copy(
            update={
                "status": PendingActionStatus.EXECUTED,
                "approved_by": approved_by,
                "approved_at": now,
                "updated_at": now,
                "execution_message": f"canonical_promoted:{written_path.as_posix()}",
            }
        )
        self.action_queue_service.update_action(scope, updated_action)
        return updated_action, (
            f"动作执行结果：{action.action_id} {action.title}\n"
            f"- 已写入 canonical convention v{promotion_request.target_version}\n"
            f"- 路径：{written_path.as_posix()}"
        )

    def _require_promotable_candidate(self, tenant_id: str, candidate_id: str) -> SkillCandidate:
        candidate = self.skill_registry.load_candidate(tenant_id, candidate_id)
        if candidate is None:
            raise ValueError(f"未找到 skill candidate：{candidate_id}")
        if candidate.status not in {SkillCandidateStatus.APPROVED, SkillCandidateStatus.ACTIVE}:
            raise ValueError("只有 approved 或 active 的 skill candidate 才能推广为 canonical 规范。")
        return candidate

    def _build_promotion_request(
        self,
        *,
        candidate: SkillCandidate,
        requested_by: str,
    ) -> CanonicalConventionPromotionRequest:
        target_version = self.canonical_convention_service.next_version(
            candidate.tenant_id,
            candidate.candidate_id,
        )
        canonical_document = self._build_canonical_document(candidate, version=target_version)
        return CanonicalConventionPromotionRequest(
            candidate_id=candidate.candidate_id,
            candidate_name=candidate.name,
            workflow=candidate.workflow,
            requested_by=requested_by,
            target_convention_id=canonical_document.convention_id,
            target_version=target_version,
            canonical_document=canonical_document,
        )

    def _build_canonical_document(
        self,
        candidate: SkillCandidate,
        *,
        version: int,
    ) -> CanonicalConventionDocument:
        focus_areas = self._extract_review_focus_areas(candidate)
        policy_scope = (
            CanonicalPolicyScope.REVIEW
            if candidate.workflow == "review"
            else CanonicalPolicyScope.INCIDENT
        )
        policy_tags = ["policy", candidate.workflow, *[item.value for item in focus_areas]]
        policy_document = CanonicalPolicyDocument(
            doc_id=f"{candidate.candidate_id}-policy",
            title=f"Approved {candidate.name} Policy",
            content=self._render_policy_document(candidate),
            scope=policy_scope,
            source_uri=(
                f"canonical://{candidate.tenant_id}/{candidate.candidate_id}/"
                f"{candidate.candidate_id}-policy"
            ),
            tags=policy_tags,
        )
        review_defaults = (
            OrgReviewDefaults(default_focus_areas=focus_areas)
            if focus_areas
            else None
        )
        return CanonicalConventionDocument(
            convention_id=candidate.candidate_id,
            version=version,
            title=f"{candidate.name} Canonical Convention",
            status=CanonicalConventionStatus.APPROVED,
            review_defaults=review_defaults,
            policy_documents=[policy_document],
        )

    def _extract_review_focus_areas(self, candidate: SkillCandidate) -> list[ReviewFocusArea]:
        if candidate.workflow != "review":
            return []

        focus_areas: list[ReviewFocusArea] = []
        for token in candidate.source_pattern_key.split("/"):
            try:
                focus_area = ReviewFocusArea(token)
            except ValueError:
                continue
            if focus_area not in focus_areas:
                focus_areas.append(focus_area)
        return focus_areas

    def _render_policy_document(self, candidate: SkillCandidate) -> str:
        sections = [
            f"Candidate: {candidate.name}",
            f"Workflow: {candidate.workflow}",
            f"Pattern: {candidate.source_pattern_key}",
            "",
            "Trigger Conditions:",
            *self._render_list(candidate.trigger_conditions),
            "",
            "Steps:",
            *self._render_list(candidate.steps),
            "",
            "Verification:",
            *self._render_list(candidate.verification_steps),
            "",
            "Failure Signals:",
            *self._render_list(candidate.failure_signals),
        ]
        return "\n".join(sections).strip()

    def _render_list(self, items: list[str]) -> list[str]:
        if not items:
            return ["- none"]
        return [f"- {item}" for item in items]
