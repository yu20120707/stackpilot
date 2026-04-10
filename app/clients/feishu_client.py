from __future__ import annotations

from dataclasses import dataclass
import json

import httpx

from app.models.contracts import FeishuReplySendResult, FeishuThreadLoadResponse


@dataclass(slots=True)
class FeishuClientConfig:
    base_url: str
    tenant_access_token: str
    timeout_seconds: int = 30


class FeishuClient:
    def __init__(
        self,
        config: FeishuClientConfig | None = None,
        *,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.config = config
        self.http_client = http_client

    async def fetch_thread_messages(
        self,
        *,
        chat_id: str,
        message_id: str,
        thread_id: str,
    ) -> FeishuThreadLoadResponse:
        raise NotImplementedError("Feishu thread loading will be implemented in THR-001/REP-001 integrations.")

    async def reply_to_thread(
        self,
        *,
        chat_id: str,
        thread_id: str,
        trigger_message_id: str,
        reply_text: str,
    ) -> FeishuReplySendResult:
        if self.config is None or self.http_client is None:
            raise NotImplementedError("Feishu reply sending requires an HTTP client and config.")

        request_body = {
            "chat_id": chat_id,
            "thread_id": thread_id,
            "msg_type": "text",
            "content": json.dumps({"text": reply_text}, ensure_ascii=False),
        }
        headers = {
            "Authorization": f"Bearer {self.config.tenant_access_token}",
            "Content-Type": "application/json",
        }

        try:
            response = await self.http_client.post(
                f"{self.config.base_url.rstrip('/')}/im/v1/messages/{trigger_message_id}/reply",
                headers=headers,
                json=request_body,
            )
        except httpx.TimeoutException:
            return FeishuReplySendResult(
                success=False,
                error_code="reply_failed",
                error_message="feishu_send_timeout",
            )
        except httpx.HTTPError:
            return FeishuReplySendResult(
                success=False,
                error_code="reply_failed",
                error_message="feishu_send_failed",
            )

        if response.is_error:
            return FeishuReplySendResult(
                success=False,
                error_code="reply_failed",
                error_message="feishu_send_failed",
            )

        try:
            payload = response.json()
            reply_message_id = payload["data"]["message_id"]
        except (ValueError, KeyError, TypeError):
            return FeishuReplySendResult(
                success=False,
                error_code="reply_failed",
                error_message="feishu_send_failed",
            )

        if not isinstance(reply_message_id, str) or not reply_message_id.strip():
            return FeishuReplySendResult(
                success=False,
                error_code="reply_failed",
                error_message="feishu_send_failed",
            )

        return FeishuReplySendResult(
            success=True,
            reply_message_id=reply_message_id.strip(),
        )

    async def aclose(self) -> None:
        if self.http_client is not None:
            await self.http_client.aclose()
