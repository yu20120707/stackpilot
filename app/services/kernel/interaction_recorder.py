from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from app.core.logging import get_logger
from app.models.contracts import ActionScope, AuditLogEntry, InteractionRecord
from app.services.kernel.audit_log_service import AuditLogService

logger = get_logger(__name__)


class InteractionRecorder:
    def __init__(
        self,
        base_dir: Path,
        *,
        audit_log_service: AuditLogService,
    ) -> None:
        self.base_dir = base_dir
        self.audit_log_service = audit_log_service

    def record(self, scope: ActionScope, record: InteractionRecord) -> None:
        existing_records = self.list_thread_records(scope)
        if any(existing.correlation_key == record.correlation_key for existing in existing_records):
            return

        path = self._thread_record_path(scope)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.model_dump(mode="json"), ensure_ascii=False))
            handle.write("\n")

        self.audit_log_service.append_entry(
            scope.tenant_id,
            AuditLogEntry(
                event_id=record.event_id,
                event_type=record.event_type.value,
                tenant_id=record.tenant_id,
                thread_id=record.thread_id,
                occurred_at=record.occurred_at,
                summary=self._build_summary(record),
                related_action_id=record.action_id,
            ),
        )

    def list_thread_records(self, scope: ActionScope) -> list[InteractionRecord]:
        return self._load_records(self._thread_record_path(scope))

    def list_tenant_records(self, tenant_id: str) -> list[InteractionRecord]:
        tenant_dir = self.base_dir / tenant_id / "threads"
        if not tenant_dir.exists():
            return []

        records: list[InteractionRecord] = []
        for path in sorted(tenant_dir.glob("*.jsonl")):
            records.extend(self._load_records(path))
        records.sort(key=lambda item: item.occurred_at)
        return records

    def _thread_record_path(self, scope: ActionScope) -> Path:
        return self.base_dir / scope.tenant_id / "threads" / f"{scope.thread_id}.jsonl"

    def _load_records(self, path: Path) -> list[InteractionRecord]:
        if not path.exists():
            return []

        records: list[InteractionRecord] = []
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                payload = json.loads(raw_line)
                records.append(InteractionRecord.model_validate(payload))
            except (json.JSONDecodeError, ValidationError, TypeError, ValueError):
                logger.warning("Ignoring invalid interaction record in %s.", path)
        return records

    def _build_summary(self, record: InteractionRecord) -> str:
        if record.event_type.value == "analysis_reply_sent":
            status = record.summary_status.value if record.summary_status is not None else "unknown"
            return f"analysis_reply_sent:{status}"
        if record.event_type.value == "actions_proposed":
            return f"actions_proposed:{record.payload.get('action_count', 0)}"
        if record.event_type.value == "action_executed":
            if record.action_id:
                return f"action_executed:{record.action_id}"
            return "action_executed"
        return record.event_type.value
