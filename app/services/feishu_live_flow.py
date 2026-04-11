from __future__ import annotations

from datetime import datetime, timezone

from app.clients.feishu_client import FeishuClient
from app.core.logging import get_logger
from app.models.contracts import (
    AnalysisRequest,
    AnalysisResultStatus,
    NormalizedFeishuMessageEvent,
    StructuredSummary,
    TemporaryFailureReply,
    ThreadMessage,
    ThreadMemoryState,
    TriggerCommand,
)
from app.services.analysis_service import AnalysisService
from app.services.kernel.memory_service import MemoryService
from app.services.knowledge_base import KnowledgeBase
from app.services.reply_renderer import ReplyRenderer
from app.services.thread_reader import ThreadReader

logger = get_logger(__name__)


class FeishuLiveFlow:
    def __init__(
        self,
        *,
        feishu_client: FeishuClient,
        thread_reader: ThreadReader,
        knowledge_base: KnowledgeBase,
        analysis_service: AnalysisService,
        reply_renderer: ReplyRenderer,
        memory_service: MemoryService | None = None,
    ) -> None:
        self.feishu_client = feishu_client
        self.thread_reader = thread_reader
        self.memory_service = memory_service
        self.knowledge_base = knowledge_base
        self.analysis_service = analysis_service
        self.reply_renderer = reply_renderer

    async def process_trigger(
        self,
        *,
        trigger_command: TriggerCommand,
        trigger_event: NormalizedFeishuMessageEvent,
    ) -> None:
        logger.info(
            "Feishu live flow started: command=%s chat_id=%s thread_id=%s message_id=%s",
            trigger_command.value,
            trigger_event.chat_id,
            trigger_event.thread_id,
            trigger_event.message_id,
        )
        try:
            analysis_request = await self.thread_reader.build_analysis_request(
                trigger_command=trigger_command,
                trigger_event=trigger_event,
            )
            logger.info(
                "Thread loaded for message_id=%s: messages=%s",
                trigger_event.message_id,
                len(analysis_request.thread_messages),
            )
            citations = self.knowledge_base.retrieve_citations(analysis_request)
            logger.info(
                "Knowledge retrieval complete for message_id=%s: citations=%s",
                trigger_event.message_id,
                len(citations),
            )
            reply_payload = await self.analysis_service.summarize(
                analysis_request,
                citations=citations,
            )
            logger.info(
                "Analysis complete for message_id=%s: status=%s",
                trigger_event.message_id,
                getattr(reply_payload, "status", "unknown"),
            )
        except Exception:
            logger.exception(
                "Feishu live flow failed before reply generation for thread_id=%s message_id=%s.",
                trigger_event.thread_id,
                trigger_event.message_id,
            )
            analysis_request = self._build_fallback_request(
                trigger_command=trigger_command,
                trigger_event=trigger_event,
            )
            reply_payload = TemporaryFailureReply(
                status=AnalysisResultStatus.TEMPORARY_FAILURE,
                headline="本次分析暂未完成",
                known_facts=[trigger_event.message_text],
                missing_information=["完整线程上下文"],
                citations=[],
                retry_hint="请稍后重试，或补充更多上下文后再次触发。",
            )

        reply_text = self.reply_renderer.render_for_trigger(
            reply_payload,
            trigger_command=trigger_command,
        )
        logger.info(
            "Reply rendered for message_id=%s: chars=%s",
            analysis_request.trigger_message_id,
            len(reply_text),
        )
        send_result = await self.feishu_client.reply_to_thread(
            chat_id=analysis_request.chat_id,
            thread_id=analysis_request.thread_id,
            trigger_message_id=analysis_request.trigger_message_id,
            reply_text=reply_text,
        )
        if not send_result.success:
            logger.warning(
                "Feishu reply send failed for thread_id=%s message_id=%s error=%s.",
                analysis_request.thread_id,
                analysis_request.trigger_message_id,
                send_result.error_message,
            )
            return

        logger.info(
            "Feishu live flow completed for thread_id=%s trigger_message_id=%s reply_message_id=%s.",
            analysis_request.thread_id,
            analysis_request.trigger_message_id,
            send_result.reply_message_id,
        )
        self._persist_thread_state(
            trigger_event=trigger_event,
            trigger_command=trigger_command,
            analysis_request=analysis_request,
            reply_payload=reply_payload,
            reply_text=reply_text,
            reply_message_id=send_result.reply_message_id,
        )

    def _build_fallback_request(
        self,
        *,
        trigger_command: TriggerCommand,
        trigger_event: NormalizedFeishuMessageEvent,
    ) -> AnalysisRequest:
        return AnalysisRequest(
            trigger_command=trigger_command,
            chat_id=trigger_event.chat_id,
            thread_id=trigger_event.thread_id,
            trigger_message_id=trigger_event.message_id,
            user_id=trigger_event.sender_id,
            user_display_name=trigger_event.sender_name,
            thread_messages=[
                ThreadMessage(
                    message_id=trigger_event.message_id,
                    sender_name=trigger_event.sender_name or "Unknown",
                    sent_at=trigger_event.event_time,
                    text=trigger_event.message_text,
                )
            ],
        )

    def _persist_thread_state(
        self,
        *,
        trigger_event: NormalizedFeishuMessageEvent,
        trigger_command: TriggerCommand,
        analysis_request: AnalysisRequest,
        reply_payload: StructuredSummary | TemporaryFailureReply,
        reply_text: str,
        reply_message_id: str | None,
    ) -> None:
        if self.memory_service is None or not isinstance(reply_payload, StructuredSummary):
            return

        scope = self.memory_service.resolve_scope(trigger_event)
        latest_message = analysis_request.thread_messages[-1]
        thread_state = ThreadMemoryState(
            last_summary_text=reply_text,
            last_summary_message_id=reply_message_id,
            last_processed_message_id=latest_message.message_id,
            last_processed_at=latest_message.sent_at,
            last_trigger_command=trigger_command,
            last_summary_status=reply_payload.status,
            updated_at=datetime.now(timezone.utc),
            known_facts=reply_payload.known_facts[:5],
            open_questions=reply_payload.missing_information[:5],
        )

        try:
            self.memory_service.save_thread_state(scope, thread_state)
        except Exception:
            logger.exception(
                "Failed to persist thread memory for thread_id=%s trigger_message_id=%s.",
                analysis_request.thread_id,
                analysis_request.trigger_message_id,
            )
