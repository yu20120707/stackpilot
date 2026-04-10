import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


FIXTURES_DIR = Path(__file__).parent / "fixtures" / "feishu"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


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
