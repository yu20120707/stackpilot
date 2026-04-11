from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
from typing import Any

import httpx

from app.core.logging import get_logger
from app.models.contracts import FeishuReplySendResult, FeishuThreadLoadResponse
from app.models.contracts import FeishuThreadMessageRecord

logger = get_logger(__name__)
MAX_HISTORY_PAGE_SIZE = 50

@dataclass(slots=True)
class FeishuClientConfig:
    base_url: str
    tenant_access_token: str | None = None
    app_id: str | None = None
    app_secret: str | None = None
    timeout_seconds: int = 30
    token_refresh_buffer_seconds: int = 300


class FeishuClient:
    def __init__(
        self,
        config: FeishuClientConfig | None = None,
        *,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.config = config
        self.http_client = http_client or (
            httpx.AsyncClient(timeout=config.timeout_seconds)
            if config is not None
            else None
        )
        self._token_lock = asyncio.Lock()
        self._cached_tenant_access_token: str | None = None
        self._cached_tenant_access_token_expires_at: datetime | None = None

    async def fetch_thread_messages(
        self,
        *,
        chat_id: str,
        message_id: str,
        thread_id: str,
    ) -> FeishuThreadLoadResponse:
        if self.config is None or self.http_client is None:
            raise NotImplementedError("Feishu thread loading requires an HTTP client and config.")

        headers = await self._build_auth_headers()
        if headers is None:
            return FeishuThreadLoadResponse(thread_messages=[])

        params: dict[str, Any] = {
            "container_id_type": "thread",
            "container_id": thread_id,
            "sort_type": "ByCreateTimeDesc",
            "page_size": MAX_HISTORY_PAGE_SIZE,
        }
        records: list[FeishuThreadMessageRecord] = []
        page_token: str | None = None

        while len(records) < MAX_HISTORY_PAGE_SIZE:
            request_params = dict(params)
            if page_token:
                request_params["page_token"] = page_token

            try:
                response = await self.http_client.get(
                    f"{self.config.base_url.rstrip('/')}/im/v1/messages",
                    headers=headers,
                    params=request_params,
                )
            except httpx.TimeoutException:
                logger.warning(
                    "Timed out while loading Feishu thread messages for thread_id=%s chat_id=%s.",
                    thread_id,
                    chat_id,
                )
                break
            except httpx.HTTPError:
                logger.warning(
                    "HTTP failure while loading Feishu thread messages for thread_id=%s chat_id=%s.",
                    thread_id,
                    chat_id,
                )
                break

            if response.is_error:
                logger.warning(
                    "Feishu thread load failed with status=%s for thread_id=%s chat_id=%s.",
                    response.status_code,
                    thread_id,
                    chat_id,
                )
                break

            try:
                payload = response.json()
            except ValueError:
                logger.warning(
                    "Feishu thread load returned invalid JSON for thread_id=%s chat_id=%s.",
                    thread_id,
                    chat_id,
                )
                break

            if payload.get("code") != 0:
                logger.warning(
                    "Feishu thread load returned code=%s msg=%s for thread_id=%s chat_id=%s.",
                    payload.get("code"),
                    payload.get("msg"),
                    thread_id,
                    chat_id,
                )
                break

            data = payload.get("data")
            if not isinstance(data, dict):
                break

            items = data.get("items")
            if not isinstance(items, list):
                break

            for item in items:
                record = self._parse_thread_message_record(item)
                if record is not None:
                    records.append(record)
                if len(records) >= MAX_HISTORY_PAGE_SIZE:
                    break

            has_more = data.get("has_more") is True
            next_page_token = data.get("page_token")
            if (
                not has_more
                or not isinstance(next_page_token, str)
                or not next_page_token.strip()
            ):
                break
            page_token = next_page_token.strip()

        records.sort(key=self._thread_record_sort_key)
        return FeishuThreadLoadResponse(thread_messages=records)

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

        headers = await self._build_auth_headers()
        if headers is None:
            return FeishuReplySendResult(
                success=False,
                error_code="reply_failed",
                error_message="feishu_auth_failed",
            )

        request_body = {
            "msg_type": "text",
            "content": json.dumps({"text": reply_text}, ensure_ascii=False),
            "reply_in_thread": True,
            "uuid": self._build_reply_uuid(
                chat_id=chat_id,
                thread_id=thread_id,
                trigger_message_id=trigger_message_id,
            ),
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
            if payload.get("code") != 0:
                raise ValueError("Feishu reply returned a non-zero code.")
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

    async def _build_auth_headers(self) -> dict[str, str] | None:
        token = await self._get_tenant_access_token()
        if token is None:
            return None

        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        }

    async def _get_tenant_access_token(self) -> str | None:
        if self.config is None:
            return None

        static_token = self._normalize_optional_text(self.config.tenant_access_token)
        if static_token:
            return static_token

        if self.http_client is None:
            return None

        if not self._needs_token_refresh():
            return self._cached_tenant_access_token

        async with self._token_lock:
            if not self._needs_token_refresh():
                return self._cached_tenant_access_token

            app_id = self._normalize_optional_text(self.config.app_id)
            app_secret = self._normalize_optional_text(self.config.app_secret)
            if not app_id or not app_secret:
                logger.warning("Feishu client is missing both tenant token and app credentials.")
                return None

            try:
                response = await self.http_client.post(
                    f"{self.config.base_url.rstrip('/')}/auth/v3/tenant_access_token/internal",
                    headers={"Content-Type": "application/json; charset=utf-8"},
                    json={
                        "app_id": app_id,
                        "app_secret": app_secret,
                    },
                )
            except httpx.TimeoutException:
                logger.warning("Timed out while requesting Feishu tenant_access_token.")
                return None
            except httpx.HTTPError:
                logger.warning("HTTP failure while requesting Feishu tenant_access_token.")
                return None

            if response.is_error:
                logger.warning(
                    "Feishu tenant_access_token request failed with status=%s.",
                    response.status_code,
                )
                return None

            try:
                payload = response.json()
            except ValueError:
                logger.warning("Feishu tenant_access_token response did not contain valid JSON.")
                return None

            if payload.get("code") != 0:
                logger.warning(
                    "Feishu tenant_access_token request returned code=%s msg=%s.",
                    payload.get("code"),
                    payload.get("msg"),
                )
                return None

            tenant_access_token = self._normalize_optional_text(payload.get("tenant_access_token"))
            expire_seconds = payload.get("expire")
            if tenant_access_token is None or not isinstance(expire_seconds, int):
                logger.warning("Feishu tenant_access_token response was missing token or expiry.")
                return None

            self._cached_tenant_access_token = tenant_access_token
            self._cached_tenant_access_token_expires_at = datetime.now(timezone.utc) + timedelta(
                seconds=expire_seconds
            )
            return tenant_access_token

    def _needs_token_refresh(self) -> bool:
        if not self._cached_tenant_access_token or self._cached_tenant_access_token_expires_at is None:
            return True

        refresh_deadline = self._cached_tenant_access_token_expires_at - timedelta(
            seconds=self.config.token_refresh_buffer_seconds if self.config else 300
        )
        return datetime.now(timezone.utc) >= refresh_deadline

    def _parse_thread_message_record(self, item: object) -> FeishuThreadMessageRecord | None:
        if not isinstance(item, dict):
            return None

        message_id = self._normalize_optional_text(item.get("message_id"))
        if message_id is None:
            return None

        sent_at = self._parse_timestamp(item.get("create_time"))
        sender_name = self._extract_sender_name(item.get("sender"))

        body = item.get("body")
        body_content = body.get("content") if isinstance(body, dict) else None
        text = self._extract_message_text(body_content or item.get("content"))

        return FeishuThreadMessageRecord(
            message_id=message_id,
            sender_name=sender_name,
            sent_at=sent_at,
            text=text,
        )

    def _parse_timestamp(self, value: object) -> datetime | None:
        if isinstance(value, str):
            normalized = value.strip()
            if not normalized:
                return None

            if normalized.isdigit():
                timestamp = int(normalized)
                if timestamp > 10_000_000_000:
                    return datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)
                return datetime.fromtimestamp(timestamp, tz=timezone.utc)

            try:
                return datetime.fromisoformat(normalized.replace("Z", "+00:00"))
            except ValueError:
                return None

        if isinstance(value, (int, float)):
            timestamp = float(value)
            if timestamp > 10_000_000_000:
                return datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)
            return datetime.fromtimestamp(timestamp, tz=timezone.utc)

        return None

    def _extract_sender_name(self, sender: object) -> str | None:
        if not isinstance(sender, dict):
            return None

        sender_id = self._normalize_optional_text(sender.get("id"))
        if sender_id:
            return sender_id

        return self._normalize_optional_text(sender.get("sender_type"))

    def _extract_message_text(self, content: object) -> str | None:
        if isinstance(content, str):
            stripped = content.strip()
            if not stripped:
                return None

            if stripped.startswith("{") and stripped.endswith("}"):
                try:
                    decoded = json.loads(stripped)
                except json.JSONDecodeError:
                    return stripped

                if isinstance(decoded, dict):
                    text = self._normalize_optional_text(decoded.get("text"))
                    return text or stripped

            return stripped

        if isinstance(content, dict):
            return self._normalize_optional_text(content.get("text"))

        return None

    def _thread_record_sort_key(self, record: FeishuThreadMessageRecord) -> tuple[datetime, str]:
        return (record.sent_at or datetime.min.replace(tzinfo=timezone.utc), record.message_id)

    def _build_reply_uuid(
        self,
        *,
        chat_id: str,
        thread_id: str,
        trigger_message_id: str,
    ) -> str:
        digest = hashlib.sha1(
            f"{chat_id}:{thread_id}:{trigger_message_id}".encode("utf-8")
        ).hexdigest()[:16]
        return f"reply-{digest}"

    def _normalize_optional_text(self, value: object) -> str | None:
        if not isinstance(value, str):
            return None

        normalized = value.strip()
        return normalized or None
