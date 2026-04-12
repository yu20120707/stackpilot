import json
from pathlib import Path

import pytest

from app.clients.feishu_client import FeishuClient
from app.models.contracts import (
    AnalysisResultStatus,
    FeishuThreadLoadResponse,
    FollowUpSource,
    MemoryScope,
    NormalizedFeishuMessageEvent,
    ThreadMemoryState,
    TriggerCommand,
)
from app.services.kernel.memory_service import MemoryService
from app.services.incident.thread_reader import ThreadReader


FIXTURES_DIR = Path(__file__).parent / "fixtures" / "feishu"


class FakeFeishuClient(FeishuClient):
    def __init__(self, thread_payload: dict) -> None:
        self.thread_payload = thread_payload
        self.calls: list[tuple[str, str, str]] = []

    async def fetch_thread_messages(
        self,
        *,
        chat_id: str,
        message_id: str,
        thread_id: str,
    ) -> FeishuThreadLoadResponse:
        self.calls.append((chat_id, message_id, thread_id))
        return FeishuThreadLoadResponse.model_validate(self.thread_payload)


class FakeMemoryService:
    def __init__(self, thread_state: ThreadMemoryState | None) -> None:
        self.thread_state = thread_state
        self.scopes: list[MemoryScope] = []

    def resolve_scope(self, trigger_event: NormalizedFeishuMessageEvent) -> MemoryScope:
        scope = MemoryScope(
            tenant_id=trigger_event.chat_id,
            user_id=trigger_event.sender_id,
            thread_id=trigger_event.thread_id,
        )
        self.scopes.append(scope)
        return scope

    def load_thread_state(self, scope: MemoryScope) -> ThreadMemoryState | None:
        _ = scope
        return self.thread_state


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


def build_trigger_event() -> NormalizedFeishuMessageEvent:
    return NormalizedFeishuMessageEvent(
        chat_id="oc_xxx",
        message_id="om_trigger",
        thread_id="omt_xxx",
        sender_id="ou_xxx",
        sender_name="Alice",
        message_text="@机器人 分析一下这次故障",
        mentions_bot=True,
        event_time="2026-04-10T01:03:00+08:00",
    )


@pytest.mark.anyio
async def test_thread_reader_builds_analysis_request_from_thread_fixture() -> None:
    client = FakeFeishuClient(load_fixture("thread_messages.json"))
    reader = ThreadReader(client, max_thread_messages=50)

    request = await reader.build_analysis_request(
        trigger_command=TriggerCommand.ANALYZE_INCIDENT,
        trigger_event=build_trigger_event(),
    )

    assert client.calls == [("oc_xxx", "om_trigger", "omt_xxx")]
    assert request.trigger_command is TriggerCommand.ANALYZE_INCIDENT
    assert [message.message_id for message in request.thread_messages] == ["om_1", "om_3"]
    assert request.thread_messages[1].sender_name == "Unknown"
    assert request.thread_messages[1].text == "we rolled back payment-api and error rate is dropping"


@pytest.mark.anyio
async def test_thread_reader_falls_back_to_trigger_message_when_thread_is_empty() -> None:
    client = FakeFeishuClient({"thread_messages": []})
    reader = ThreadReader(client, max_thread_messages=50)

    request = await reader.build_analysis_request(
        trigger_command=TriggerCommand.ANALYZE_INCIDENT,
        trigger_event=build_trigger_event(),
    )

    assert len(request.thread_messages) == 1
    assert request.thread_messages[0].message_id == "om_trigger"
    assert request.thread_messages[0].sender_name == "Alice"
    assert request.thread_messages[0].text == "@机器人 分析一下这次故障"


@pytest.mark.anyio
async def test_thread_reader_keeps_latest_messages_within_limit() -> None:
    client = FakeFeishuClient(
        {
            "thread_messages": [
                {
                    "message_id": "om_1",
                    "sender_name": "A",
                    "sent_at": "2026-04-10T01:00:00+08:00",
                    "text": "first"
                },
                {
                    "message_id": "om_2",
                    "sender_name": "B",
                    "sent_at": "2026-04-10T01:01:00+08:00",
                    "text": "second"
                },
                {
                    "message_id": "om_3",
                    "sender_name": "C",
                    "sent_at": "2026-04-10T01:02:00+08:00",
                    "text": "third"
                }
            ]
        }
    )
    reader = ThreadReader(client, max_thread_messages=2)

    request = await reader.build_analysis_request(
        trigger_command=TriggerCommand.SUMMARIZE_THREAD,
        trigger_event=build_trigger_event(),
    )

    assert [message.message_id for message in request.thread_messages] == ["om_2", "om_3"]


@pytest.mark.anyio
async def test_thread_reader_prefers_memory_backed_follow_up_context() -> None:
    client = FakeFeishuClient(
        {
            "thread_messages": [
                {
                    "message_id": "om_1",
                    "sender_name": "AlertBot",
                    "sent_at": "2026-04-10T01:00:00+08:00",
                    "text": "payment service 5xx spike",
                },
                {
                    "message_id": "om_bot_1",
                    "sender_name": "IncidentBot",
                    "sent_at": "2026-04-10T01:03:00+08:00",
                    "text": "plain bot reply without summary markers",
                },
                {
                    "message_id": "om_2",
                    "sender_name": "Alice",
                    "sent_at": "2026-04-10T01:05:00+08:00",
                    "text": "补充信息：回滚后错误率继续下降",
                },
                {
                    "message_id": "om_3",
                    "sender_name": "Bob",
                    "sent_at": "2026-04-10T01:06:00+08:00",
                    "text": "@机器人 基于最新信息重试",
                },
            ]
        }
    )
    memory_service = FakeMemoryService(
        ThreadMemoryState(
            last_summary_text="当前判断：支付服务异常可能与最近发布有关。",
            last_summary_message_id="om_bot_1",
            last_processed_message_id="om_1",
            last_processed_at="2026-04-10T01:00:00+08:00",
            last_trigger_command=TriggerCommand.ANALYZE_INCIDENT,
            last_summary_status=AnalysisResultStatus.SUCCESS,
            updated_at="2026-04-10T01:03:00+08:00",
            known_facts=["已执行回滚"],
            open_questions=["错误日志"],
        )
    )
    reader = ThreadReader(client, memory_service=memory_service, max_thread_messages=50)

    request = await reader.build_analysis_request(
        trigger_command=TriggerCommand.RERUN_ANALYSIS,
        trigger_event=build_trigger_event(),
    )

    assert memory_service.scopes
    assert request.follow_up_context is not None
    assert request.follow_up_context.source is FollowUpSource.MEMORY
    assert request.follow_up_context.previous_summary == "当前判断：支付服务异常可能与最近发布有关。"
    assert [message.message_id for message in request.follow_up_context.new_messages] == ["om_2", "om_3"]


@pytest.mark.anyio
async def test_thread_reader_falls_back_to_heuristic_when_memory_is_missing() -> None:
    client = FakeFeishuClient(load_fixture("thread_messages_follow_up.json"))
    reader = ThreadReader(
        client,
        memory_service=FakeMemoryService(None),
        max_thread_messages=50,
    )

    request = await reader.build_analysis_request(
        trigger_command=TriggerCommand.RERUN_ANALYSIS,
        trigger_event=build_trigger_event(),
    )

    assert request.follow_up_context is not None
    assert request.follow_up_context.source is FollowUpSource.HEURISTIC
    assert "当前判断：" in (request.follow_up_context.previous_summary or "")


def test_memory_service_round_trips_thread_state(tmp_path: Path) -> None:
    service = MemoryService(tmp_path / "memory")
    scope = service.resolve_scope(build_trigger_event())
    state = ThreadMemoryState(
        last_summary_text="当前判断：支付服务异常可能与最近发布有关。",
        last_summary_message_id="om_bot_1",
        last_processed_message_id="om_3",
        last_processed_at="2026-04-10T01:06:00+08:00",
        last_trigger_command=TriggerCommand.RERUN_ANALYSIS,
        last_summary_status=AnalysisResultStatus.SUCCESS,
        updated_at="2026-04-10T01:07:00+08:00",
        known_facts=["已执行回滚"],
        open_questions=["详细错误日志"],
    )

    service.save_thread_state(scope, state)

    snapshot = service.load_snapshot(scope)
    loaded_state = service.load_thread_state(scope)

    assert loaded_state is not None
    assert loaded_state.last_summary_message_id == "om_bot_1"
    assert loaded_state.last_processed_message_id == "om_3"
    assert loaded_state.last_trigger_command is TriggerCommand.RERUN_ANALYSIS
    assert snapshot.thread_memory is not None
    assert snapshot.user_memory == {}
    assert snapshot.org_memory == {}
