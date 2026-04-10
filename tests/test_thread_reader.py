import json
from pathlib import Path

import pytest

from app.clients.feishu_client import FeishuClient
from app.models.contracts import (
    FeishuThreadLoadResponse,
    NormalizedFeishuMessageEvent,
    TriggerCommand,
)
from app.services.thread_reader import ThreadReader


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
