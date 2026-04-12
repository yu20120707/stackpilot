from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from app.core.logging import get_logger
from app.models.contracts import AuditLogEntry, SkillCandidate, SkillCandidateStatus
from app.services.kernel.audit_log_service import AuditLogService

logger = get_logger(__name__)


class SkillRegistry:
    def __init__(self, base_dir: Path, *, audit_log_service: AuditLogService | None = None) -> None:
        self.base_dir = base_dir
        self.audit_log_service = audit_log_service

    def list_candidates(self, tenant_id: str) -> list[SkillCandidate]:
        tenant_dir = self.base_dir / tenant_id
        if not tenant_dir.exists():
            return []

        candidates: list[SkillCandidate] = []
        for path in sorted(tenant_dir.glob("*/skill.json")):
            candidate = self._load_candidate_from_path(path)
            if candidate is not None:
                candidates.append(candidate)
        return candidates

    def find_by_pattern(self, tenant_id: str, pattern_key: str) -> SkillCandidate | None:
        for candidate in self.list_candidates(tenant_id):
            if candidate.source_pattern_key == pattern_key:
                return candidate
        return None

    def load_candidate(self, tenant_id: str, candidate_id: str) -> SkillCandidate | None:
        path = self._candidate_json_path(tenant_id, candidate_id)
        return self._load_candidate_from_path(path)

    def upsert_candidate(self, candidate: SkillCandidate) -> SkillCandidate:
        candidate_dir = self._candidate_dir(candidate.tenant_id, candidate.candidate_id)
        candidate_dir.mkdir(parents=True, exist_ok=True)
        self._candidate_json_path(candidate.tenant_id, candidate.candidate_id).write_text(
            json.dumps(candidate.model_dump(mode="json", exclude_none=True), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._candidate_markdown_path(candidate.tenant_id, candidate.candidate_id).write_text(
            self._render_markdown(candidate),
            encoding="utf-8",
        )
        return candidate

    def create_draft_candidate(self, candidate: SkillCandidate) -> SkillCandidate:
        existing = self.load_candidate(candidate.tenant_id, candidate.candidate_id)
        if existing is not None:
            return existing
        created = self.upsert_candidate(candidate)
        self._append_audit_entry(created, "candidate_created", created.candidate_id)
        return created

    def approve_candidate(self, tenant_id: str, candidate_id: str, approved_by: str) -> SkillCandidate:
        candidate = self._require_candidate(tenant_id, candidate_id)
        now = datetime.now(timezone.utc)
        updated = candidate.model_copy(
            update={
                "status": SkillCandidateStatus.APPROVED,
                "approved_by": approved_by,
                "approved_at": now,
                "updated_at": now,
            }
        )
        approved = self.upsert_candidate(updated)
        self._append_audit_entry(approved, "candidate_approved", approved_by)
        return approved

    def activate_candidate(self, tenant_id: str, candidate_id: str, activated_by: str) -> SkillCandidate:
        candidate = self._require_candidate(tenant_id, candidate_id)
        if candidate.status is not SkillCandidateStatus.APPROVED:
            raise ValueError("Skill candidates must be approved before activation.")

        now = datetime.now(timezone.utc)
        updated = candidate.model_copy(
            update={
                "status": SkillCandidateStatus.ACTIVE,
                "activated_by": activated_by,
                "activated_at": now,
                "updated_at": now,
            }
        )
        activated = self.upsert_candidate(updated)
        self._append_audit_entry(activated, "candidate_activated", activated_by)
        return activated

    def retire_candidate(self, tenant_id: str, candidate_id: str) -> SkillCandidate:
        candidate = self._require_candidate(tenant_id, candidate_id)
        updated = candidate.model_copy(
            update={
                "status": SkillCandidateStatus.RETIRED,
                "updated_at": datetime.now(timezone.utc),
            }
        )
        retired = self.upsert_candidate(updated)
        self._append_audit_entry(retired, "candidate_retired", candidate_id)
        return retired

    def _require_candidate(self, tenant_id: str, candidate_id: str) -> SkillCandidate:
        candidate = self.load_candidate(tenant_id, candidate_id)
        if candidate is None:
            raise ValueError(f"Unknown skill candidate: {candidate_id}")
        return candidate

    def _candidate_dir(self, tenant_id: str, candidate_id: str) -> Path:
        return self.base_dir / tenant_id / candidate_id

    def _candidate_json_path(self, tenant_id: str, candidate_id: str) -> Path:
        return self._candidate_dir(tenant_id, candidate_id) / "skill.json"

    def _candidate_markdown_path(self, tenant_id: str, candidate_id: str) -> Path:
        return self._candidate_dir(tenant_id, candidate_id) / "SKILL.md"

    def _load_candidate_from_path(self, path: Path) -> SkillCandidate | None:
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return SkillCandidate.model_validate(payload)
        except (OSError, ValueError, TypeError, json.JSONDecodeError, ValidationError):
            logger.warning("Ignoring invalid skill candidate file at %s.", path)
            return None

    def _render_markdown(self, candidate: SkillCandidate) -> str:
        lines = [
            f"# {candidate.name}",
            "",
            f"- Candidate ID: `{candidate.candidate_id}`",
            f"- Workflow: `{candidate.workflow}`",
            f"- Status: `{candidate.status.value}`",
            f"- Pattern Key: `{candidate.source_pattern_key}`",
            "",
            "## Trigger Conditions",
            *self._render_list(candidate.trigger_conditions),
            "",
            "## Steps",
            *self._render_list(candidate.steps),
            "",
            "## Verification",
            *self._render_list(candidate.verification_steps),
            "",
            "## Failure Signals",
            *self._render_list(candidate.failure_signals),
            "",
            "## Evidence",
            *self._render_list(candidate.evidence_event_ids),
        ]
        return "\n".join(lines).strip() + "\n"

    def _render_list(self, items: list[str]) -> list[str]:
        if not items:
            return ["- none"]
        return [f"- {item}" for item in items]

    def _append_audit_entry(
        self,
        candidate: SkillCandidate,
        event_type: str,
        marker: str,
    ) -> None:
        if self.audit_log_service is None:
            return
        self.audit_log_service.append_entry(
            candidate.tenant_id,
            AuditLogEntry(
                event_id=f"{candidate.candidate_id}-{event_type}",
                event_type=event_type,
                tenant_id=candidate.tenant_id,
                thread_id="skill-registry",
                occurred_at=datetime.now(timezone.utc),
                summary=f"{event_type}:{candidate.candidate_id}:{marker}",
                related_action_id=None,
            ),
        )
