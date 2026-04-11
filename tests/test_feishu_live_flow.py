import json
from datetime import datetime
from pathlib import Path

import pytest

from app.clients.feishu_client import FeishuClient
from app.models.contracts import (
    ActionScope,
    FeishuReplySendResult,
    FeishuThreadLoadResponse,
    NormalizedFeishuMessageEvent,
    TriggerCommand,
)
from app.services.analysis_service import AnalysisService
from app.services.feishu_live_flow import FeishuLiveFlow
from app.services.incident_action_service import IncidentActionService
from app.services.kernel.action_queue_service import ActionQueueService
from app.services.kernel.memory_service import MemoryService
from app.services.knowledge_base import KnowledgeBase
from app.services.postmortem_renderer import PostmortemRenderer
from app.services.postmortem_service import PostmortemService
from app.services.reply_renderer import ReplyRenderer
from app.services.task_sync_service import TaskSyncService
from app.services.thread_reader import ThreadReader


FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_json(*relative_parts: str) -> dict:
    return json.loads(FIXTURES_DIR.joinpath(*relative_parts).read_text(encoding="utf-8"))


def load_text(*relative_parts: str) -> str:
    return FIXTURES_DIR.joinpath(*relative_parts).read_text(encoding="utf-8")


class FakeLiveFeishuClient(FeishuClient):
    def __init__(self, thread_payload: dict, *, reply_success: bool = True) -> None:
        super().__init__()
        self.thread_payload = thread_payload
        self.reply_success = reply_success
        self.reply_calls: list[tuple[str, str, str, str]] = []

    async def fetch_thread_messages(
        self,
        *,
        chat_id: str,
        message_id: str,
        thread_id: str,
    ) -> FeishuThreadLoadResponse:
        _ = (chat_id, message_id, thread_id)
        return FeishuThreadLoadResponse.model_validate(self.thread_payload)

    async def reply_to_thread(
        self,
        *,
        chat_id: str,
        thread_id: str,
        trigger_message_id: str,
        reply_text: str,
    ) -> FeishuReplySendResult:
        self.reply_calls.append((chat_id, thread_id, trigger_message_id, reply_text))
        if not self.reply_success:
            return FeishuReplySendResult(
                success=False,
                error_code="reply_failed",
                error_message="feishu_send_failed",
            )

        return FeishuReplySendResult(success=True, reply_message_id="om_reply_live")


class FakeLLMClient:
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[tuple[str, str]] = []

    async def generate_structured_summary(self, *, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        return self.response


class FakeTaskSyncClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def create_task(self, *, target, draft):  # noqa: ANN001
        self.calls.append(draft.title)
        return {
            "title": draft.title,
            "external_id": f"TASK-{len(self.calls)}",
            "external_url": f"https://tasks.example.local/{len(self.calls)}",
        }


def build_trigger_event() -> NormalizedFeishuMessageEvent:
    payload = load_json("feishu", "supported_message_event.json")
    event = payload["event"]
    message = event["message"]
    return NormalizedFeishuMessageEvent(
        chat_id=message["chat_id"],
        message_id=message["message_id"],
        thread_id=message["thread_id"],
        sender_id=event["sender"]["sender_id"]["open_id"],
        sender_name=event["sender"]["sender_name"],
        message_text="分析一下这次故障",
        mentions_bot=True,
        event_time=datetime.fromisoformat("2026-04-10T01:00:00+08:00"),
    )


@pytest.mark.anyio
async def test_feishu_live_flow_runs_analysis_and_replies(tmp_path: Path) -> None:
    feishu_client = FakeLiveFeishuClient(load_json("feishu", "thread_messages.json"))
    llm_client = FakeLLMClient(load_text("analysis", "structured_summary_success.json"))
    memory_service = MemoryService(tmp_path / "memory")
    live_flow = FeishuLiveFlow(
        feishu_client=feishu_client,
        thread_reader=ThreadReader(feishu_client, memory_service=memory_service),
        memory_service=memory_service,
        knowledge_base=KnowledgeBase(FIXTURES_DIR / "knowledge", max_hits=3),
        analysis_service=AnalysisService(
            llm_client,
            prompt_path=Path("app/prompts/analysis_prompt.md"),
        ),
        reply_renderer=ReplyRenderer(),
    )

    await live_flow.process_trigger(
        trigger_command=TriggerCommand.ANALYZE_INCIDENT,
        trigger_event=build_trigger_event(),
    )

    assert llm_client.calls
    assert len(feishu_client.reply_calls) == 1
    assert feishu_client.reply_calls[0][0:3] == ("oc_xxx", "omt_xxx", "om_xxx")
    assert "Payment Release 2026-04-10" in feishu_client.reply_calls[0][3]
    saved_state = memory_service.load_thread_state(memory_service.resolve_scope(build_trigger_event()))
    assert saved_state is not None
    assert saved_state.last_summary_message_id == "om_reply_live"
    assert saved_state.last_processed_message_id == "om_3"
    assert saved_state.last_trigger_command is TriggerCommand.ANALYZE_INCIDENT


@pytest.mark.anyio
async def test_feishu_live_flow_sends_temporary_failure_reply_on_unexpected_error() -> None:
    class BrokenThreadReader:
        async def build_analysis_request(self, *, trigger_command, trigger_event):
            _ = (trigger_command, trigger_event)
            raise RuntimeError("boom")

    class UnusedKnowledgeBase:
        def retrieve_citations(self, analysis_request):
            _ = analysis_request
            return []

    class UnusedAnalysisService:
        async def summarize(self, request, *, citations=None):
            _ = (request, citations)
            raise AssertionError("summarize should not be called")

    feishu_client = FakeLiveFeishuClient(load_json("feishu", "thread_messages.json"))
    live_flow = FeishuLiveFlow(
        feishu_client=feishu_client,
        thread_reader=BrokenThreadReader(),
        memory_service=None,
        knowledge_base=UnusedKnowledgeBase(),
        analysis_service=UnusedAnalysisService(),
        reply_renderer=ReplyRenderer(),
    )

    await live_flow.process_trigger(
        trigger_command=TriggerCommand.ANALYZE_INCIDENT,
        trigger_event=build_trigger_event(),
    )

    assert len(feishu_client.reply_calls) == 1
    assert "分析暂未完成" in feishu_client.reply_calls[0][3]


@pytest.mark.anyio
async def test_feishu_live_flow_does_not_persist_thread_state_when_reply_send_fails(tmp_path: Path) -> None:
    feishu_client = FakeLiveFeishuClient(
        load_json("feishu", "thread_messages.json"),
        reply_success=False,
    )
    llm_client = FakeLLMClient(load_text("analysis", "structured_summary_success.json"))
    memory_service = MemoryService(tmp_path / "memory")
    live_flow = FeishuLiveFlow(
        feishu_client=feishu_client,
        thread_reader=ThreadReader(feishu_client, memory_service=memory_service),
        memory_service=memory_service,
        knowledge_base=KnowledgeBase(FIXTURES_DIR / "knowledge", max_hits=3),
        analysis_service=AnalysisService(
            llm_client,
            prompt_path=Path("app/prompts/analysis_prompt.md"),
        ),
        reply_renderer=ReplyRenderer(),
    )

    await live_flow.process_trigger(
        trigger_command=TriggerCommand.ANALYZE_INCIDENT,
        trigger_event=build_trigger_event(),
    )

    assert len(feishu_client.reply_calls) == 1
    assert memory_service.load_thread_state(memory_service.resolve_scope(build_trigger_event())) is None


@pytest.mark.anyio
async def test_feishu_live_flow_persists_pending_actions_for_summarize_thread(tmp_path: Path) -> None:
    feishu_client = FakeLiveFeishuClient(load_json("feishu", "thread_messages.json"))
    llm_client = FakeLLMClient(load_text("analysis", "structured_summary_success.json"))
    memory_service = MemoryService(tmp_path / "memory")
    action_queue_service = ActionQueueService(tmp_path / "actions")
    incident_action_service = IncidentActionService(
        action_queue_service=action_queue_service,
        task_sync_service=TaskSyncService(),
        postmortem_service=PostmortemService(llm_client),
        postmortem_renderer=PostmortemRenderer(),
    )
    live_flow = FeishuLiveFlow(
        feishu_client=feishu_client,
        thread_reader=ThreadReader(feishu_client, memory_service=memory_service),
        memory_service=memory_service,
        knowledge_base=KnowledgeBase(FIXTURES_DIR / "knowledge", max_hits=3),
        analysis_service=AnalysisService(
            llm_client,
            prompt_path=Path("app/prompts/analysis_prompt.md"),
        ),
        reply_renderer=ReplyRenderer(),
        incident_action_service=incident_action_service,
    )

    await live_flow.process_trigger(
        trigger_command=TriggerCommand.SUMMARIZE_THREAD,
        trigger_event=build_trigger_event(),
    )

    scope = ActionScope(tenant_id="oc_xxx", thread_id="omt_xxx")
    pending_actions = action_queue_service.list_pending_actions(scope)
    assert [action.action_id for action in pending_actions] == ["A1", "A2"]
    assert "待审批动作：" in feishu_client.reply_calls[0][3]
    assert "批准动作 A1" in feishu_client.reply_calls[0][3]


@pytest.mark.anyio
async def test_feishu_live_flow_discards_pending_actions_when_summary_reply_send_fails(tmp_path: Path) -> None:
    feishu_client = FakeLiveFeishuClient(
        load_json("feishu", "thread_messages.json"),
        reply_success=False,
    )
    llm_client = FakeLLMClient(load_text("analysis", "structured_summary_success.json"))
    action_queue_service = ActionQueueService(tmp_path / "actions")
    incident_action_service = IncidentActionService(
        action_queue_service=action_queue_service,
        task_sync_service=TaskSyncService(),
        postmortem_service=PostmortemService(llm_client),
        postmortem_renderer=PostmortemRenderer(),
    )
    live_flow = FeishuLiveFlow(
        feishu_client=feishu_client,
        thread_reader=ThreadReader(feishu_client, memory_service=MemoryService(tmp_path / "memory")),
        memory_service=MemoryService(tmp_path / "memory-2"),
        knowledge_base=KnowledgeBase(FIXTURES_DIR / "knowledge", max_hits=3),
        analysis_service=AnalysisService(
            llm_client,
            prompt_path=Path("app/prompts/analysis_prompt.md"),
        ),
        reply_renderer=ReplyRenderer(),
        incident_action_service=incident_action_service,
    )

    await live_flow.process_trigger(
        trigger_command=TriggerCommand.SUMMARIZE_THREAD,
        trigger_event=build_trigger_event(),
    )

    scope = ActionScope(tenant_id="oc_xxx", thread_id="omt_xxx")
    assert action_queue_service.list_pending_actions(scope) == []


@pytest.mark.anyio
async def test_feishu_live_flow_executes_approved_task_action(tmp_path: Path) -> None:
    thread_payload = load_json("feishu", "thread_messages.json")
    feishu_client = FakeLiveFeishuClient(thread_payload)
    llm_client = FakeLLMClient(load_text("analysis", "structured_summary_success.json"))
    action_queue_service = ActionQueueService(tmp_path / "actions")
    task_sync_client = FakeTaskSyncClient()
    incident_action_service = IncidentActionService(
        action_queue_service=action_queue_service,
        task_sync_service=TaskSyncService(task_sync_client=task_sync_client),
        postmortem_service=PostmortemService(llm_client),
        postmortem_renderer=PostmortemRenderer(),
    )
    live_flow = FeishuLiveFlow(
        feishu_client=feishu_client,
        thread_reader=ThreadReader(feishu_client, memory_service=MemoryService(tmp_path / "memory")),
        memory_service=MemoryService(tmp_path / "memory-2"),
        knowledge_base=KnowledgeBase(FIXTURES_DIR / "knowledge", max_hits=3),
        analysis_service=AnalysisService(
            llm_client,
            prompt_path=Path("app/prompts/analysis_prompt.md"),
        ),
        reply_renderer=ReplyRenderer(),
        incident_action_service=incident_action_service,
    )

    await live_flow.process_trigger(
        trigger_command=TriggerCommand.SUMMARIZE_THREAD,
        trigger_event=build_trigger_event(),
    )

    approval_event = build_trigger_event().model_copy(
        update={
            "message_id": "om_approve_1",
            "message_text": "批准动作 A1",
        }
    )
    await live_flow.process_trigger(
        trigger_command=TriggerCommand.APPROVE_ACTION,
        trigger_event=approval_event,
    )

    scope = ActionScope(tenant_id="oc_xxx", thread_id="omt_xxx")
    persisted_action = action_queue_service.find_action(scope, "A1")
    assert persisted_action is not None
    assert persisted_action.status.value == "executed"
    assert task_sync_client.calls == ["补充错误日志", "确认最近一次发布内容", "持续观察回滚后的错误率变化"]
    assert len(feishu_client.reply_calls) == 2
    assert "动作执行结果：A1 同步待办草稿" in feishu_client.reply_calls[1][3]
