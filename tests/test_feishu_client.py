import json

import httpx
import pytest

from app.clients.feishu_client import FeishuClient, FeishuClientConfig
from app.models.contracts import FeishuThreadLoadResponse


def build_reply_text() -> str:
    return "当前判断：支付服务异常正在恢复。"


@pytest.mark.anyio
async def test_feishu_client_sends_reply_and_returns_message_id() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers["Authorization"]
        captured["body"] = request.content.decode("utf-8")
        return httpx.Response(
            200,
            json={"code": 0, "msg": "ok", "data": {"message_id": "om_reply_xxx"}},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = FeishuClient(
            FeishuClientConfig(
                base_url="https://unit.test/open-apis",
                tenant_access_token="tenant-token",
            ),
            http_client=http_client,
        )

        result = await client.reply_to_thread(
            chat_id="oc_xxx",
            thread_id="omt_xxx",
            trigger_message_id="om_trigger",
            reply_text=build_reply_text(),
        )

    body = json.loads(captured["body"])
    assert result.success is True
    assert result.reply_message_id == "om_reply_xxx"
    assert captured["url"].endswith("/open-apis/im/v1/messages/om_trigger/reply")
    assert captured["authorization"] == "Bearer tenant-token"
    assert body["msg_type"] == "text"
    assert body["reply_in_thread"] is True
    assert body["uuid"].startswith("reply-")
    assert json.loads(body["content"])["text"] == build_reply_text()


@pytest.mark.anyio
async def test_feishu_client_returns_failure_result_on_http_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        _ = request
        return httpx.Response(500, json={"msg": "failure"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = FeishuClient(
            FeishuClientConfig(
                base_url="https://unit.test/open-apis",
                tenant_access_token="tenant-token",
            ),
            http_client=http_client,
        )

        result = await client.reply_to_thread(
            chat_id="oc_xxx",
            thread_id="omt_xxx",
            trigger_message_id="om_trigger",
            reply_text=build_reply_text(),
        )

    assert result.success is False
    assert result.error_code == "reply_failed"
    assert result.error_message == "feishu_send_failed"


@pytest.mark.anyio
async def test_feishu_client_fetches_tenant_token_and_thread_messages() -> None:
    seen_requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_requests.append(str(request.url))

        if request.url.path.endswith("/auth/v3/tenant_access_token/internal"):
            assert json.loads(request.content.decode("utf-8")) == {
                "app_id": "cli_live",
                "app_secret": "secret_live",
            }
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": "ok",
                    "tenant_access_token": "tenant-token",
                    "expire": 7200,
                },
            )

        assert request.url.path.endswith("/im/v1/messages")
        assert request.headers["Authorization"] == "Bearer tenant-token"
        assert request.url.params["container_id_type"] == "thread"
        assert request.url.params["container_id"] == "omt_xxx"
        assert request.url.params["sort_type"] == "ByCreateTimeDesc"
        assert request.url.params["page_size"] == "50"
        return httpx.Response(
            200,
            json={
                "code": 0,
                "msg": "ok",
                "data": {
                    "has_more": False,
                    "items": [
                        {
                            "message_id": "om_2",
                            "create_time": "1712710860000",
                            "sender": {
                                "id": "cli_bot",
                                "sender_type": "app",
                            },
                            "body": {
                                "content": "{\"text\":\"rollback completed\"}",
                            },
                        },
                        {
                            "message_id": "om_1",
                            "create_time": "1712710800000",
                            "sender": {
                                "id": "ou_alert",
                                "sender_type": "user",
                            },
                            "body": {
                                "content": "{\"text\":\"payment service 5xx spike\"}",
                            },
                        },
                    ],
                },
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = FeishuClient(
            FeishuClientConfig(
                base_url="https://unit.test/open-apis",
                app_id="cli_live",
                app_secret="secret_live",
            ),
            http_client=http_client,
        )

        result = await client.fetch_thread_messages(
            chat_id="oc_xxx",
            message_id="om_trigger",
            thread_id="omt_xxx",
        )

    assert isinstance(result, FeishuThreadLoadResponse)
    assert [message.message_id for message in result.thread_messages] == ["om_1", "om_2"]
    assert [message.text for message in result.thread_messages] == [
        "payment service 5xx spike",
        "rollback completed",
    ]
    assert seen_requests[0].endswith("/open-apis/auth/v3/tenant_access_token/internal")
    assert "container_id=omt_xxx" in seen_requests[1]
