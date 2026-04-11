from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from app.core.logging import get_logger
from app.models.contracts import (
    ActionQueueState,
    ActionScope,
    NormalizedFeishuMessageEvent,
    PendingActionStatus,
    PendingActionType,
    PendingIncidentAction,
)

logger = get_logger(__name__)


class ActionQueueService:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir

    def resolve_scope(self, trigger_event: NormalizedFeishuMessageEvent) -> ActionScope:
        return ActionScope(
            tenant_id=trigger_event.chat_id,
            thread_id=trigger_event.thread_id,
        )

    def load_state(self, scope: ActionScope) -> ActionQueueState:
        path = self._thread_queue_path(scope)
        payload = self._load_json_mapping(path)
        if not payload:
            return ActionQueueState(
                updated_at=datetime.now(timezone.utc),
                actions=[],
            )

        try:
            return ActionQueueState.model_validate(payload)
        except ValidationError:
            logger.warning("Ignoring invalid action queue state at %s.", path)
            return ActionQueueState(
                updated_at=datetime.now(timezone.utc),
                actions=[],
            )

    def list_pending_actions(self, scope: ActionScope) -> list[PendingIncidentAction]:
        return [
            action
            for action in self.load_state(scope).actions
            if action.status is PendingActionStatus.PENDING_APPROVAL
        ]

    def allocate_action_id(self, scope: ActionScope) -> str:
        next_index = 1
        for action in self.load_state(scope).actions:
            if not action.action_id.startswith("A"):
                continue
            raw_index = action.action_id[1:]
            if raw_index.isdigit():
                next_index = max(next_index, int(raw_index) + 1)
        return f"A{next_index}"

    def enqueue_actions(
        self,
        scope: ActionScope,
        actions: list[PendingIncidentAction],
    ) -> list[PendingIncidentAction]:
        if not actions:
            return []

        state = self.load_state(scope)
        replaced_types = {action.action_type for action in actions}
        existing_actions = [
            existing
            for existing in state.actions
            if not (
                existing.status is PendingActionStatus.PENDING_APPROVAL
                and existing.action_type in replaced_types
            )
        ]
        next_state = ActionQueueState(
            schema_version=state.schema_version,
            updated_at=datetime.now(timezone.utc),
            actions=[*existing_actions, *actions],
        )
        self._save_state(scope, next_state)
        return actions

    def find_action(
        self,
        scope: ActionScope,
        action_id: str,
    ) -> PendingIncidentAction | None:
        normalized_action_id = action_id.upper()
        for action in self.load_state(scope).actions:
            if action.action_id == normalized_action_id:
                return action
        return None

    def update_action(
        self,
        scope: ActionScope,
        action: PendingIncidentAction,
    ) -> None:
        state = self.load_state(scope)
        updated = False
        next_actions: list[PendingIncidentAction] = []
        for existing in state.actions:
            if existing.action_id == action.action_id:
                next_actions.append(action)
                updated = True
                continue
            next_actions.append(existing)

        if not updated:
            next_actions.append(action)

        next_state = ActionQueueState(
            schema_version=state.schema_version,
            updated_at=datetime.now(timezone.utc),
            actions=next_actions,
        )
        self._save_state(scope, next_state)

    def remove_actions(self, scope: ActionScope, action_ids: list[str]) -> None:
        if not action_ids:
            return

        normalized_action_ids = {action_id.upper() for action_id in action_ids}
        state = self.load_state(scope)
        next_state = ActionQueueState(
            schema_version=state.schema_version,
            updated_at=datetime.now(timezone.utc),
            actions=[
                action
                for action in state.actions
                if action.action_id not in normalized_action_ids
            ],
        )
        self._save_state(scope, next_state)

    def _tenant_dir(self, scope: ActionScope) -> Path:
        return self.base_dir / scope.tenant_id

    def _thread_queue_path(self, scope: ActionScope) -> Path:
        return self._tenant_dir(scope) / "threads" / f"{scope.thread_id}.json"

    def _save_state(self, scope: ActionScope, state: ActionQueueState) -> None:
        path = self._thread_queue_path(scope)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(path.suffix + ".tmp")
        serialized = json.dumps(
            state.model_dump(mode="json", exclude_none=True),
            ensure_ascii=False,
            indent=2,
        )
        temp_path.write_text(serialized, encoding="utf-8")
        temp_path.replace(path)

    def _load_json_mapping(self, path: Path) -> dict[str, object]:
        if not path.exists():
            return {}

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            logger.warning("Ignoring unreadable action queue file at %s.", path)
            return {}

        if not isinstance(payload, dict):
            logger.warning("Ignoring non-object action queue file at %s.", path)
            return {}

        return payload
