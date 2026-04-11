from __future__ import annotations

from datetime import datetime, timezone

from app.models.contracts import (
    InteractionEventType,
    InteractionRecord,
    PendingActionType,
    SkillCandidate,
    SkillCandidateStatus,
)
from app.services.kernel.interaction_recorder import InteractionRecorder
from app.services.skill_registry import SkillRegistry


class SkillMiner:
    def __init__(
        self,
        *,
        interaction_recorder: InteractionRecorder,
        skill_registry: SkillRegistry,
    ) -> None:
        self.interaction_recorder = interaction_recorder
        self.skill_registry = skill_registry

    def evaluate_tenant(self, tenant_id: str) -> list[SkillCandidate]:
        records = self.interaction_recorder.list_tenant_records(tenant_id)
        created_candidates: list[SkillCandidate] = []

        for pattern_key, action_type in self._iter_supported_patterns(records):
            if self.skill_registry.find_by_pattern(tenant_id, pattern_key) is not None:
                continue

            matching_records = [
                record
                for record in records
                if record.event_type is InteractionEventType.ACTION_EXECUTED
                and record.pattern_key == pattern_key
                and record.payload.get("execution_status") == "executed"
            ]
            if len(matching_records) < 2:
                continue

            candidate = SkillCandidate(
                candidate_id=self._candidate_id_for(action_type),
                tenant_id=tenant_id,
                name=self._candidate_name_for(action_type),
                workflow="incident",
                status=SkillCandidateStatus.DRAFT,
                source_pattern_key=pattern_key,
                trigger_conditions=self._trigger_conditions_for(action_type),
                steps=self._steps_for(action_type),
                verification_steps=self._verification_steps_for(action_type),
                failure_signals=self._failure_signals_for(action_type),
                evidence_event_ids=[record.event_id for record in matching_records[-2:]],
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            created_candidates.append(self.skill_registry.create_draft_candidate(candidate))

        return created_candidates

    def _iter_supported_patterns(
        self,
        records: list[InteractionRecord],
    ) -> list[tuple[str, PendingActionType]]:
        patterns: dict[str, PendingActionType] = {}
        for record in records:
            if (
                record.event_type is not InteractionEventType.ACTION_EXECUTED
                or record.pattern_key is None
                or record.action_type is None
            ):
                continue
            patterns[record.pattern_key] = record.action_type
        return sorted(patterns.items())

    def _candidate_id_for(self, action_type: PendingActionType) -> str:
        if action_type is PendingActionType.TASK_SYNC:
            return "skill-incident-task-sync-approval"
        return "skill-incident-postmortem-writeback"

    def _candidate_name_for(self, action_type: PendingActionType) -> str:
        if action_type is PendingActionType.TASK_SYNC:
            return "incident-task-sync-approval-loop"
        return "incident-postmortem-writeback-loop"

    def _trigger_conditions_for(self, action_type: PendingActionType) -> list[str]:
        if action_type is PendingActionType.TASK_SYNC:
            return [
                "A summarize-thread run produced pending task-sync actions.",
                "A user approved the task-sync action from the same Feishu thread.",
            ]
        return [
            "A summarize-thread run produced a pending postmortem draft action.",
            "A user approved the postmortem action from the same Feishu thread.",
        ]

    def _steps_for(self, action_type: PendingActionType) -> list[str]:
        if action_type is PendingActionType.TASK_SYNC:
            return [
                "Build external task drafts from the structured summary.",
                "Persist the task-sync action in the thread action queue.",
                "Wait for an explicit approval command such as '批准动作 A1'.",
                "Execute the confirmed task sync and write the result back to the same thread.",
            ]
        return [
            "Build a reviewable postmortem draft from the thread summary and citations.",
            "Persist the postmortem action in the thread action queue.",
            "Wait for an explicit approval command such as '批准动作 A2'.",
            "Write the rendered draft back to the same thread and mark the action executed.",
        ]

    def _verification_steps_for(self, action_type: PendingActionType) -> list[str]:
        if action_type is PendingActionType.TASK_SYNC:
            return [
                "The action status becomes executed in the queue.",
                "The reply written to the thread includes synced task references.",
            ]
        return [
            "The action status becomes executed in the queue.",
            "The reply written to the thread includes the rendered postmortem draft.",
        ]

    def _failure_signals_for(self, action_type: PendingActionType) -> list[str]:
        if action_type is PendingActionType.TASK_SYNC:
            return [
                "external_task_sync_failed",
                "thread reply send failure after approval",
            ]
        return [
            "postmortem draft missing from the pending action payload",
            "thread reply send failure after approval",
        ]
