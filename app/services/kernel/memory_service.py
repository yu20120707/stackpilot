from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from app.core.logging import get_logger
from app.models.contracts import (
    MemoryScope,
    MemorySnapshot,
    NormalizedFeishuMessageEvent,
    ThreadMemoryState,
)

logger = get_logger(__name__)


class MemoryService:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir

    def resolve_scope(self, trigger_event: NormalizedFeishuMessageEvent) -> MemoryScope:
        return MemoryScope(
            tenant_id=trigger_event.chat_id,
            user_id=trigger_event.sender_id,
            thread_id=trigger_event.thread_id,
        )

    def load_snapshot(self, scope: MemoryScope) -> MemorySnapshot:
        return MemorySnapshot(
            user_memory=self._load_json_mapping(self._user_memory_path(scope)),
            org_memory=self._load_json_mapping(self._org_memory_path(scope)),
            thread_memory=self.load_thread_state(scope),
        )

    def load_thread_state(self, scope: MemoryScope) -> ThreadMemoryState | None:
        path = self._thread_state_path(scope)
        payload = self._load_json_mapping(path)
        if not payload:
            return None

        try:
            return ThreadMemoryState.model_validate(payload)
        except ValidationError:
            logger.warning("Ignoring invalid thread memory state at %s.", path)
            return None

    def save_thread_state(self, scope: MemoryScope, state: ThreadMemoryState) -> None:
        path = self._thread_state_path(scope)
        path.parent.mkdir(parents=True, exist_ok=True)

        temp_path = path.with_suffix(path.suffix + ".tmp")
        serialized = json.dumps(
            state.model_dump(mode="json", exclude_none=True),
            ensure_ascii=False,
            indent=2,
        )
        temp_path.write_text(serialized, encoding="utf-8")
        temp_path.replace(path)

    def _tenant_dir(self, scope: MemoryScope) -> Path:
        return self.base_dir / scope.tenant_id

    def _thread_state_path(self, scope: MemoryScope) -> Path:
        return self._tenant_dir(scope) / "threads" / f"{scope.thread_id}.json"

    def _user_memory_path(self, scope: MemoryScope) -> Path:
        return self._tenant_dir(scope) / "users" / f"{scope.user_id}.json"

    def _org_memory_path(self, scope: MemoryScope) -> Path:
        return self._tenant_dir(scope) / "org.json"

    def _load_json_mapping(self, path: Path) -> dict[str, object]:
        if not path.exists():
            return {}

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            logger.warning("Ignoring unreadable memory file at %s.", path)
            return {}

        if not isinstance(payload, dict):
            logger.warning("Ignoring non-object memory file at %s.", path)
            return {}

        return payload
