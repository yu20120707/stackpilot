from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from app.core.logging import get_logger
from app.models.contracts import AuditLogEntry

logger = get_logger(__name__)


class AuditLogService:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir

    def append_entry(self, tenant_id: str, entry: AuditLogEntry) -> None:
        path = self._audit_log_path(tenant_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry.model_dump(mode="json"), ensure_ascii=False))
            handle.write("\n")

    def list_entries(self, tenant_id: str) -> list[AuditLogEntry]:
        path = self._audit_log_path(tenant_id)
        if not path.exists():
            return []

        entries: list[AuditLogEntry] = []
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                payload = json.loads(raw_line)
                entries.append(AuditLogEntry.model_validate(payload))
            except (json.JSONDecodeError, ValidationError, TypeError, ValueError):
                logger.warning("Ignoring invalid audit log entry in %s.", path)
        return entries

    def _audit_log_path(self, tenant_id: str) -> Path:
        return self.base_dir / tenant_id / "audit.jsonl"
