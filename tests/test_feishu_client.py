import json

import httpx
import pytest

from app.clients.feishu_client import FeishuClient, FeishuClientConfig


@pytest.mark.anyio
async def test_feishu_client_sends_reply_and_returns_message_id() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers["Authorization"]
        captured["body"] = request.content.decode("utf-8")
        return httpx.Response(
            200,
            json={"data": {"message_id": "om_reply_xxx"}},
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
            reply_text="当前判断：支付服务异常正在恢复。",
        )

    body = json.loads(captured["body"])
    assert result.success is True
    assert result.reply_message_id == "om_reply_xxx"
    assert captured["url"].endswith("/open-apis/im/v1/messages/om_trigger/reply")
    assert captured["authorization"] == "Bearer tenant-token"
    assert body["chat_id"] == "oc_xxx"
    assert body["thread_id"] == "omt_xxx"
    assert json.loads(body["content"])["text"] == "当前判断：支付服务异常正在恢复。"


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
            reply_text="当前判断：支付服务异常正在恢复。",
        )

    assert result.success is False
    assert result.error_code == "reply_failed"
    assert result.error_message == "feishu_send_failed"
