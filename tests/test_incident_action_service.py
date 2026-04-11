import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.models.contracts import (
    ActionScope,
    AnalysisRequest,
    AnalysisResultStatus,
    ConfidenceLevel,
    KnowledgeCitation,
    SourceType,
    StructuredSummary,
    TaskSyncStatus,
    ThreadMessage,
    TodoDraftItem,
    TriggerCommand,
)
from app.services.incident_action_service import IncidentActionService
from app.services.kernel.action_queue_service import ActionQueueService
from app.services.kernel.canonical_convention_service import CanonicalConventionService
from app.services.kernel.memory_service import MemoryService
from app.services.kernel.org_convention_service import OrgConventionService
from app.services.postmortem_renderer import PostmortemRenderer
from app.services.postmortem_service import PostmortemService
from app.services.task_sync_service import TaskSyncService


def build_request() -> AnalysisRequest:
    return AnalysisRequest(
        trigger_command=TriggerCommand.SUMMARIZE_THREAD,
        chat_id="oc_xxx",
        thread_id="omt_xxx",
        trigger_message_id="om_xxx",
        user_id="ou_alice",
        user_display_name="Alice",
        thread_messages=[
            ThreadMessage(
                message_id="om_1",
                sender_name="AlertBot",
                sent_at=datetime.now(timezone.utc),
                text="payment service 5xx spike after release",
            )
        ],
    )


def build_summary() -> StructuredSummary:
    return StructuredSummary(
        status=AnalysisResultStatus.SUCCESS,
        confidence=ConfidenceLevel.MEDIUM,
        current_assessment="Rollback is stabilizing the payment service after the release-related spike.",
        known_facts=[
            "The payment service hit 5xx after release.",
            "The team already rolled back the change.",
        ],
        impact_scope="Payment-related requests were affected during the spike window.",
        next_actions=[
            "Confirm the final error-rate trend.",
            "Collect deployment and error-log evidence.",
        ],
        citations=[
            KnowledgeCitation(
                source_type=SourceType.KNOWLEDGE_DOC,
                label="Payment Release 2026-04-10",
                source_uri="https://kb.example.local/releases/payment-2026-04-10",
                snippet="The payment-api release touched retry middleware and idempotency handling.",
            )
        ],
        missing_information=["Detailed error logs"],
        conclusion_summary="The thread has largely converged on a release-related issue that improved after rollback.",
        todo_draft=[
            TodoDraftItem(
                title="Confirm the final error-rate trend.",
                owner_hint="待确认",
                rationale="The rollback effect still needs a final stability check.",
            )
        ],
    )


class FakeTaskSyncClient:
    def __init__(self) -> None:
        self.calls: list[bool] = []

    async def create_task(self, *, target, draft):  # noqa: ANN001
        _ = (target, draft)
        self.calls.append(True)
        return {
            "title": draft.title,
            "external_id": "TASK-1",
            "external_url": "https://tasks.example.local/1",
        }


class FakeLLMClient:
    async def generate_structured_summary(self, *, system_prompt: str, user_prompt: str) -> str:
        _ = (system_prompt, user_prompt)
        raise ValueError("force fallback")


@pytest.mark.anyio
async def test_incident_action_service_prepares_two_pending_actions(tmp_path: Path) -> None:
    prompt_path = tmp_path / "postmortem_prompt.md"
    prompt_path.write_text("Return structured JSON only.", encoding="utf-8")
    action_queue_service = ActionQueueService(tmp_path / "actions")
    service = IncidentActionService(
        action_queue_service=action_queue_service,
        task_sync_service=TaskSyncService(),
        postmortem_service=PostmortemService(FakeLLMClient(), prompt_path=prompt_path),
        postmortem_renderer=PostmortemRenderer(),
    )

    actions = await service.prepare_actions(
        scope=ActionScope(tenant_id="oc_xxx", thread_id="omt_xxx"),
        request=build_request(),
        summary=build_summary(),
    )

    assert [action.action_id for action in actions] == ["A1", "A2"]
    assert [action.action_type.value for action in actions] == ["task_sync", "postmortem_draft"]
    assert "批准动作 A1" in service.render_pending_actions(actions)
    assert actions[1].postmortem_draft is not None


@pytest.mark.anyio
async def test_incident_action_service_executes_confirmed_task_sync(tmp_path: Path) -> None:
    prompt_path = tmp_path / "postmortem_prompt.md"
    prompt_path.write_text("Return structured JSON only.", encoding="utf-8")
    fake_client = FakeTaskSyncClient()
    action_queue_service = ActionQueueService(tmp_path / "actions")
    service = IncidentActionService(
        action_queue_service=action_queue_service,
        task_sync_service=TaskSyncService(task_sync_client=fake_client),
        postmortem_service=PostmortemService(FakeLLMClient(), prompt_path=prompt_path),
        postmortem_renderer=PostmortemRenderer(),
    )
    scope = ActionScope(tenant_id="oc_xxx", thread_id="omt_xxx")
    actions = await service.prepare_actions(
        scope=scope,
        request=build_request(),
        summary=build_summary(),
    )
    service.persist_actions(scope=scope, actions=actions)

    executed_action, reply_text = await service.execute_task_sync_action(
        scope=scope,
        action_id="A1",
        approved_by="ou_reviewer",
    )

    persisted_action = action_queue_service.find_action(scope, "A1")
    assert executed_action is not None
    assert persisted_action is not None
    assert persisted_action.status.value == "executed"
    assert persisted_action.task_sync_request is not None
    assert persisted_action.task_sync_request.confirmed is True
    assert fake_client.calls == [True]
    assert "TASK-1" in reply_text or "https://tasks.example.local/1" in reply_text


@pytest.mark.anyio
async def test_incident_action_service_duplicate_approval_is_idempotent(tmp_path: Path) -> None:
    prompt_path = tmp_path / "postmortem_prompt.md"
    prompt_path.write_text("Return structured JSON only.", encoding="utf-8")
    fake_client = FakeTaskSyncClient()
    action_queue_service = ActionQueueService(tmp_path / "actions")
    service = IncidentActionService(
        action_queue_service=action_queue_service,
        task_sync_service=TaskSyncService(task_sync_client=fake_client),
        postmortem_service=PostmortemService(FakeLLMClient(), prompt_path=prompt_path),
        postmortem_renderer=PostmortemRenderer(),
    )
    scope = ActionScope(tenant_id="oc_xxx", thread_id="omt_xxx")
    actions = await service.prepare_actions(
        scope=scope,
        request=build_request(),
        summary=build_summary(),
    )
    service.persist_actions(scope=scope, actions=actions)

    await service.execute_task_sync_action(
        scope=scope,
        action_id="A1",
        approved_by="ou_reviewer",
    )
    executed_action, reply_text = await service.execute_task_sync_action(
        scope=scope,
        action_id="A1",
        approved_by="ou_reviewer",
    )

    assert executed_action is None
    assert "无需重复批准" in reply_text
    assert fake_client.calls == [True]


@pytest.mark.anyio
async def test_incident_action_service_builds_postmortem_reply_and_marks_execution(tmp_path: Path) -> None:
    prompt_path = tmp_path / "postmortem_prompt.md"
    prompt_path.write_text("Return structured JSON only.", encoding="utf-8")
    scope = ActionScope(tenant_id="oc_xxx", thread_id="omt_xxx")
    action_queue_service = ActionQueueService(tmp_path / "actions")
    service = IncidentActionService(
        action_queue_service=action_queue_service,
        task_sync_service=TaskSyncService(),
        postmortem_service=PostmortemService(FakeLLMClient(), prompt_path=prompt_path),
        postmortem_renderer=PostmortemRenderer(),
    )
    actions = await service.prepare_actions(
        scope=scope,
        request=build_request(),
        summary=build_summary(),
    )
    service.persist_actions(scope=scope, actions=actions)

    pending_action, reply_text = service.build_postmortem_reply(
        scope=scope,
        action_id="A2",
    )
    assert pending_action is not None
    assert "复盘草稿：" in reply_text

    service.mark_postmortem_action_executed(
        scope=scope,
        action=pending_action,
        approved_by="ou_reviewer",
    )

    persisted_action = action_queue_service.find_action(scope, "A2")
    assert persisted_action is not None
    assert persisted_action.status.value == "executed"
    assert persisted_action.execution_message == "postmortem_draft_written_back"


@pytest.mark.anyio
async def test_incident_action_service_uses_org_postmortem_style(tmp_path: Path) -> None:
    prompt_path = tmp_path / "postmortem_prompt.md"
    prompt_path.write_text("Return structured JSON only.", encoding="utf-8")
    scope = ActionScope(tenant_id="oc_xxx", thread_id="omt_xxx")
    action_queue_service = ActionQueueService(tmp_path / "actions")
    memory_service = MemoryService(tmp_path / "memory")
    memory_service.save_org_memory_for_tenant(
        "oc_xxx",
        {
            "postmortem_style": {
                "title_prefix": "[SEV-2]",
                "follow_up_prefix": "团队跟进：",
                "section_labels": {
                    "follow_up_actions": "团队后续动作：",
                },
            }
        },
    )
    service = IncidentActionService(
        action_queue_service=action_queue_service,
        task_sync_service=TaskSyncService(),
        postmortem_service=PostmortemService(FakeLLMClient(), prompt_path=prompt_path),
        postmortem_renderer=PostmortemRenderer(),
        org_convention_service=OrgConventionService(memory_service),
    )
    actions = await service.prepare_actions(
        scope=scope,
        request=build_request(),
        summary=build_summary(),
    )
    service.persist_actions(scope=scope, actions=actions)

    pending_action, reply_text = service.build_postmortem_reply(
        scope=scope,
        action_id="A2",
    )

    assert pending_action is not None
    assert pending_action.postmortem_draft is not None
    assert pending_action.postmortem_draft.title.startswith("[SEV-2]")
    assert "团队后续动作：" in reply_text


@pytest.mark.anyio
async def test_incident_action_service_snapshots_resolved_postmortem_style_for_writeback(
    tmp_path: Path,
) -> None:
    prompt_path = tmp_path / "postmortem_prompt.md"
    prompt_path.write_text("Return structured JSON only.", encoding="utf-8")
    scope = ActionScope(tenant_id="oc_xxx", thread_id="omt_xxx")
    action_queue_service = ActionQueueService(tmp_path / "actions")
    memory_service = MemoryService(tmp_path / "memory")
    memory_service.save_org_memory_for_tenant(
        "oc_xxx",
        {
            "postmortem_style": {
                "section_labels": {
                    "follow_up_actions": "团队后续动作：",
                },
            }
        },
    )
    knowledge_dir = tmp_path / "knowledge"
    tenant_dir = knowledge_dir / "canonical" / "oc_xxx"
    tenant_dir.mkdir(parents=True, exist_ok=True)
    (tenant_dir / "team-defaults.canonical.json").write_text(
        json.dumps(
            {
                "convention_id": "team-defaults",
                "title": "Team Defaults",
                "status": "approved",
                "postmortem_style": {
                    "title_prefix": "[SEV-2]",
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    service = IncidentActionService(
        action_queue_service=action_queue_service,
        task_sync_service=TaskSyncService(),
        postmortem_service=PostmortemService(FakeLLMClient(), prompt_path=prompt_path),
        postmortem_renderer=PostmortemRenderer(),
        org_convention_service=OrgConventionService(
            memory_service,
            canonical_convention_service=CanonicalConventionService(knowledge_dir),
        ),
    )
    actions = await service.prepare_actions(
        scope=scope,
        request=build_request(),
        summary=build_summary(),
    )
    service.persist_actions(scope=scope, actions=actions)
    memory_service.save_org_memory_for_tenant(
        "oc_xxx",
        {
            "postmortem_style": {
                "section_labels": {
                    "follow_up_actions": "已漂移动作：",
                },
                "title_prefix": "[SEV-1]",
            }
        },
    )

    pending_action, reply_text = service.build_postmortem_reply(
        scope=scope,
        action_id="A2",
    )

    assert pending_action is not None
    assert pending_action.postmortem_style_snapshot is not None
    assert pending_action.postmortem_style_snapshot.title_prefix == "[SEV-2]"
    assert "团队后续动作：" in reply_text
    assert "已漂移动作：" not in reply_text
