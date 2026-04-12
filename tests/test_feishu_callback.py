import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from app.main import app
from app.models.contracts import TriggerCommand


FIXTURES_DIR = Path(__file__).parent / "fixtures" / "feishu"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def disable_verification_token_check(monkeypatch) -> None:
    monkeypatch.setattr(app.state.settings, "feishu_verification_token", None)


def test_feishu_callback_verification_returns_challenge() -> None:
    client = TestClient(app)

    response = client.post("/api/feishu/events", json=load_fixture("url_verification.json"))

    assert response.status_code == 200
    assert response.json() == {"challenge": "challenge-string"}


def test_feishu_callback_accepts_supported_manual_trigger() -> None:
    client = TestClient(app)

    response = client.post("/api/feishu/events", json=load_fixture("supported_message_event.json"))

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["status"] == "accepted"
    assert body["data"]["trigger_command"] == "analyze_incident"
    assert body["data"]["message_event"]["chat_id"] == "oc_xxx"
    assert body["data"]["message_event"]["thread_id"] == "omt_xxx"
    assert body["data"]["message_event"]["mentions_bot"] is True


def test_feishu_callback_accepts_action_approval_command() -> None:
    class FakeWorkflowRouter:
        async def process_trigger(self, *, trigger_command, trigger_event) -> None:
            _ = (trigger_command, trigger_event)

    app.state.services.workflow_router = FakeWorkflowRouter()
    client = TestClient(app)
    payload = load_fixture("supported_message_event.json")
    payload["event"]["message"]["content"] = json.dumps(
        {"text": "@stackpilot 批准动作 A1"},
        ensure_ascii=False,
    )

    response = client.post("/api/feishu/events", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["status"] == "accepted"
    assert body["data"]["trigger_command"] == "approve_action"


def test_feishu_callback_accepts_manual_code_review_trigger() -> None:
    class FakeWorkflowRouter:
        async def process_trigger(self, *, trigger_command, trigger_event) -> None:
            _ = (trigger_command, trigger_event)

    app.state.services.workflow_router = FakeWorkflowRouter()
    client = TestClient(app)
    payload = load_fixture("supported_message_event.json")
    payload["event"]["message"]["content"] = json.dumps(
        {"text": "@stackpilot 帮我 review 这个 PR https://github.com/openai/demo/pull/12"},
        ensure_ascii=False,
    )

    response = client.post("/api/feishu/events", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["status"] == "accepted"
    assert body["data"]["trigger_command"] == "review_code"


def test_feishu_callback_accepts_review_feedback_trigger() -> None:
    class FakeWorkflowRouter:
        async def process_trigger(self, *, trigger_command, trigger_event) -> None:
            _ = (trigger_command, trigger_event)

    app.state.services.workflow_router = FakeWorkflowRouter()
    client = TestClient(app)
    payload = load_fixture("supported_message_event.json")
    payload["event"]["message"]["content"] = json.dumps(
        {"text": "@stackpilot 采纳建议 F1"},
        ensure_ascii=False,
    )

    response = client.post("/api/feishu/events", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["status"] == "accepted"
    assert body["data"]["trigger_command"] == "review_feedback"


def test_feishu_callback_accepts_review_outcome_sync_trigger() -> None:
    class FakeWorkflowRouter:
        async def process_trigger(self, *, trigger_command, trigger_event) -> None:
            _ = (trigger_command, trigger_event)

    app.state.services.workflow_router = FakeWorkflowRouter()
    client = TestClient(app)
    payload = load_fixture("supported_message_event.json")
    payload["event"]["message"]["content"] = json.dumps(
        {"text": "@stackpilot 同步 review 结果"},
        ensure_ascii=False,
    )

    response = client.post("/api/feishu/events", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["status"] == "accepted"
    assert body["data"]["trigger_command"] == "sync_review_outcome"


def test_feishu_callback_accepts_canonical_promotion_trigger() -> None:
    class FakeWorkflowRouter:
        async def process_trigger(self, *, trigger_command, trigger_event) -> None:
            _ = (trigger_command, trigger_event)

    app.state.services.workflow_router = FakeWorkflowRouter()
    client = TestClient(app)
    payload = load_fixture("supported_message_event.json")
    payload["event"]["message"]["content"] = json.dumps(
        {"text": "@stackpilot 沉淀规范 skill-review-security-focus"},
        ensure_ascii=False,
    )

    response = client.post("/api/feishu/events", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["status"] == "accepted"
    assert body["data"]["trigger_command"] == "promote_canonical"


def test_feishu_callback_ignores_unsupported_group_chatter() -> None:
    client = TestClient(app)

    response = client.post("/api/feishu/events", json=load_fixture("unsupported_message_event.json"))

    assert response.status_code == 200
    assert response.json()["data"] == {
        "status": "ignored",
        "reason": "unsupported_message",
        "trigger_command": None,
        "message_event": None,
    }


def test_feishu_callback_ignores_direct_messages() -> None:
    client = TestClient(app)

    response = client.post("/api/feishu/events", json=load_fixture("direct_message_event.json"))

    assert response.status_code == 200
    assert response.json()["data"] == {
        "status": "ignored",
        "reason": "unsupported_context",
        "trigger_command": None,
        "message_event": None,
    }


def test_feishu_callback_schedules_live_flow_for_accepted_message(monkeypatch) -> None:
    class FakeWorkflowRouter:
        def __init__(self) -> None:
            self.calls: list[tuple[TriggerCommand, str]] = []

        async def process_trigger(self, *, trigger_command, trigger_event) -> None:
            self.calls.append((trigger_command, trigger_event.message_id))

    fake_router = FakeWorkflowRouter()
    monkeypatch.setattr(app.state.services, "workflow_router", fake_router)

    client = TestClient(app)
    response = client.post("/api/feishu/events", json=load_fixture("supported_message_event.json"))

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "accepted"
    assert fake_router.calls == [(TriggerCommand.ANALYZE_INCIDENT, "om_xxx")]
