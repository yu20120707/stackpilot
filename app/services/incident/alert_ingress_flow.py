from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Mapping

from app.clients.feishu_client import FeishuClient
from app.core.logging import get_logger
from app.models.contracts import (
    AlertIngressResult,
    AnalysisRequest,
    FeishuTarget,
    IncidentSeed,
    ThreadMessage,
    TriggerCommand,
)
from app.services.incident.analysis_service import AnalysisService
from app.services.incident.reply_renderer import ReplyRenderer
from app.services.knowledge_base import KnowledgeBase

logger = get_logger(__name__)


class AlertIngressFlow:
    def __init__(
        self,
        *,
        analysis_service: AnalysisService,
        knowledge_base: KnowledgeBase,
        reply_renderer: ReplyRenderer,
        feishu_client: FeishuClient,
    ) -> None:
        self.analysis_service = analysis_service
        self.knowledge_base = knowledge_base
        self.reply_renderer = reply_renderer
        self.feishu_client = feishu_client

    def normalize_incident_seed(
        self,
        payload: Mapping[str, Any] | IncidentSeed,
    ) -> IncidentSeed:
        if isinstance(payload, IncidentSeed):
            return payload
        if not isinstance(payload, Mapping):
            raise ValueError("alert payload must be a mapping")

        raw_payload = dict(payload)
        title = self._pick_text(
            raw_payload,
            ("title", "name", "subject", "summary", "message", "alert"),
        ) or "Incoming alert"
        source = self._pick_text(
            raw_payload,
            ("source", "service", "origin", "monitor", "producer"),
        )
        summary = self._pick_text(
            raw_payload,
            ("summary", "description", "details", "body", "message"),
        )
        severity = self._pick_text(
            raw_payload,
            ("severity", "level", "priority", "status"),
        )
        evidence_lines = self._normalize_evidence_lines(raw_payload)
        if not evidence_lines:
            evidence_lines = [summary or title]

        return IncidentSeed(
            title=title,
            source=source,
            summary=summary,
            severity=severity,
            evidence_lines=evidence_lines,
            feishu_target=self._normalize_feishu_target(raw_payload.get("feishu_target")),
            raw_payload=raw_payload,
        )

    def build_analysis_request(self, seed: IncidentSeed) -> AnalysisRequest:
        trigger_message_id = (
            seed.feishu_target.trigger_message_id
            if seed.feishu_target is not None
            else self._build_synthetic_message_id(seed, suffix="trigger")
        )
        thread_id = (
            seed.feishu_target.thread_id
            if seed.feishu_target is not None
            else self._build_synthetic_message_id(seed, suffix="thread")
        )
        chat_id = seed.feishu_target.chat_id if seed.feishu_target is not None else "alert-ingress"

        return AnalysisRequest(
            trigger_command=TriggerCommand.ANALYZE_INCIDENT,
            chat_id=chat_id,
            thread_id=thread_id,
            trigger_message_id=trigger_message_id,
            user_id="alert_ingress",
            user_display_name="Alert Ingress",
            thread_messages=self._build_thread_messages(
                seed,
                trigger_message_id=trigger_message_id,
            ),
        )

    async def process_webhook(
        self,
        payload: Mapping[str, Any] | IncidentSeed,
    ) -> AlertIngressResult:
        seed = self.normalize_incident_seed(payload)
        analysis_request = self.build_analysis_request(seed)

        try:
            citations = self.knowledge_base.retrieve_citations(analysis_request)
            reply_payload = await self.analysis_service.summarize(
                analysis_request,
                citations=citations,
            )
            reply_text = self.reply_renderer.render_for_trigger(
                reply_payload,
                trigger_command=TriggerCommand.ANALYZE_INCIDENT,
            )
        except Exception:
            logger.exception(
                "Alert ingress analysis failed for thread_id=%s.",
                analysis_request.thread_id,
            )
            return AlertIngressResult(
                success=False,
                error_code="analysis_failed",
                error_message="alert_ingress_analysis_failed",
            )

        if seed.feishu_target is None:
            logger.info(
                "Alert ingress completed without Feishu anchor: thread_id=%s messages=%s.",
                analysis_request.thread_id,
                len(analysis_request.thread_messages),
            )
            return AlertIngressResult(success=True, delivered_to_feishu=False)

        try:
            send_result = await self.feishu_client.reply_to_thread(
                chat_id=seed.feishu_target.chat_id,
                thread_id=seed.feishu_target.thread_id,
                trigger_message_id=seed.feishu_target.trigger_message_id,
                reply_text=reply_text,
            )
        except Exception:
            logger.exception(
                "Alert ingress Feishu reply failed for thread_id=%s.",
                analysis_request.thread_id,
            )
            return AlertIngressResult(
                success=False,
                error_code="reply_failed",
                error_message="alert_ingress_reply_failed",
            )

        if not send_result.success:
            return AlertIngressResult(
                success=False,
                error_code=send_result.error_code or "reply_failed",
                error_message=send_result.error_message or "alert_ingress_reply_failed",
            )

        return AlertIngressResult(
            success=True,
            delivered_to_feishu=True,
            reply_message_id=send_result.reply_message_id,
        )

    def _normalize_feishu_target(self, value: object) -> FeishuTarget | None:
        if not isinstance(value, Mapping):
            return None

        chat_id = self._pick_text(value, ("chat_id",))
        thread_id = self._pick_text(value, ("thread_id",))
        trigger_message_id = self._pick_text(value, ("trigger_message_id", "message_id"))
        if not chat_id or not thread_id or not trigger_message_id:
            return None

        return FeishuTarget(
            chat_id=chat_id,
            thread_id=thread_id,
            trigger_message_id=trigger_message_id,
        )

    def _normalize_evidence_lines(self, payload: Mapping[str, Any]) -> list[str]:
        for key in ("evidence_lines", "evidence", "lines", "details", "body"):
            lines = self._coerce_text_lines(payload.get(key))
            if lines:
                return lines
        return []

    def _coerce_text_lines(self, value: object) -> list[str]:
        if isinstance(value, str):
            return [line.strip() for line in value.splitlines() if line.strip()]

        if not isinstance(value, list):
            return []

        normalized_lines: list[str] = []
        for item in value:
            line = self._extract_text(item)
            if line:
                normalized_lines.append(line)
        return normalized_lines

    def _extract_text(self, value: object) -> str | None:
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None

        if isinstance(value, Mapping):
            for key in ("text", "message", "summary", "detail", "description"):
                candidate = self._pick_text(value, (key,))
                if candidate:
                    return candidate

        return None

    def _pick_text(self, payload: Mapping[str, Any], keys: tuple[str, ...]) -> str | None:
        for key in keys:
            value = payload.get(key)
            if isinstance(value, str):
                normalized = value.strip()
                if normalized:
                    return normalized
        return None

    def _build_thread_messages(
        self,
        seed: IncidentSeed,
        *,
        trigger_message_id: str,
    ) -> list[ThreadMessage]:
        now = datetime.now(timezone.utc)
        messages = [
            ThreadMessage(
                message_id=trigger_message_id,
                sender_name="Alert Ingress",
                sent_at=now,
                text=self._render_seed_root_message(seed),
            )
        ]

        for index, evidence_line in enumerate(seed.evidence_lines, start=1):
            messages.append(
                ThreadMessage(
                    message_id=f"{trigger_message_id}-evidence-{index}",
                    sender_name="Alert Evidence",
                    sent_at=now,
                    text=evidence_line,
                )
            )

        return messages

    def _render_seed_root_message(self, seed: IncidentSeed) -> str:
        lines = [f"Alert: {seed.title}"]
        if seed.source:
            lines.append(f"Source: {seed.source}")
        if seed.severity:
            lines.append(f"Severity: {seed.severity}")
        if seed.summary and seed.summary != seed.title:
            lines.append(f"Summary: {seed.summary}")
        return "\n".join(lines)

    def _build_synthetic_message_id(self, seed: IncidentSeed, *, suffix: str) -> str:
        digest = hashlib.sha1(
            "|".join(
                [
                    seed.title,
                    seed.source or "",
                    seed.summary or "",
                    seed.severity or "",
                    *seed.evidence_lines[:5],
                ]
            ).encode("utf-8")
        ).hexdigest()[:12]
        return f"alert-{suffix}-{digest}"
