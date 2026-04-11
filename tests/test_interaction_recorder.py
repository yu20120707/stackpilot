from datetime import datetime, timezone
from pathlib import Path

from app.models.contracts import (
    ActionScope,
    InteractionEventType,
    InteractionRecord,
    TriggerCommand,
)
from app.services.kernel.audit_log_service import AuditLogService
from app.services.kernel.interaction_recorder import InteractionRecorder


def build_record(*, event_id: str, correlation_key: str) -> InteractionRecord:
    return InteractionRecord(
        event_id=event_id,
        correlation_key=correlation_key,
        event_type=InteractionEventType.ANALYSIS_REPLY_SENT,
        tenant_id="oc_xxx",
        thread_id="omt_xxx",
        actor_id="ou_alice",
        occurred_at=datetime.now(timezone.utc),
        trigger_command=TriggerCommand.ANALYZE_INCIDENT,
        payload={"headline": "Rollback reduced the error rate."},
    )


def test_interaction_recorder_appends_and_dedupes_by_correlation_key(tmp_path: Path) -> None:
    audit_log_service = AuditLogService(tmp_path / "records")
    recorder = InteractionRecorder(
        tmp_path / "records",
        audit_log_service=audit_log_service,
    )
    scope = ActionScope(tenant_id="oc_xxx", thread_id="omt_xxx")

    recorder.record(scope, build_record(event_id="evt-1", correlation_key="analysis:om_1"))
    recorder.record(scope, build_record(event_id="evt-2", correlation_key="analysis:om_1"))

    thread_records = recorder.list_thread_records(scope)
    audit_entries = audit_log_service.list_entries("oc_xxx")

    assert len(thread_records) == 1
    assert thread_records[0].event_id == "evt-1"
    assert len(audit_entries) == 1
    assert audit_entries[0].event_type == "analysis_reply_sent"


def test_interaction_recorder_keeps_tenant_and_thread_isolation(tmp_path: Path) -> None:
    audit_log_service = AuditLogService(tmp_path / "records")
    recorder = InteractionRecorder(
        tmp_path / "records",
        audit_log_service=audit_log_service,
    )
    first_scope = ActionScope(tenant_id="oc_xxx", thread_id="omt_xxx")
    second_scope = ActionScope(tenant_id="oc_xxx", thread_id="omt_yyy")

    recorder.record(first_scope, build_record(event_id="evt-1", correlation_key="analysis:om_1"))
    recorder.record(
        second_scope,
        InteractionRecord(
            event_id="evt-2",
            correlation_key="analysis:om_2",
            event_type=InteractionEventType.REPLY_SEND_FAILED,
            tenant_id="oc_xxx",
            thread_id="omt_yyy",
            actor_id="ou_bob",
            occurred_at=datetime.now(timezone.utc),
            trigger_command=TriggerCommand.SUMMARIZE_THREAD,
            payload={"error_message": "reply_failed"},
        ),
    )

    assert [record.event_id for record in recorder.list_thread_records(first_scope)] == ["evt-1"]
    assert [record.event_id for record in recorder.list_thread_records(second_scope)] == ["evt-2"]
    assert [entry.event_id for entry in audit_log_service.list_entries("oc_xxx")] == ["evt-1", "evt-2"]
