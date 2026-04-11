from __future__ import annotations

from datetime import datetime, timezone

from app.clients.feishu_client import FeishuClient
from app.core.logging import get_logger
from app.models.contracts import (
    ActionScope,
    AnalysisRequest,
    AnalysisResultStatus,
    InteractionEventType,
    InteractionRecord,
    NormalizedFeishuMessageEvent,
    PendingActionType,
    PendingIncidentAction,
    StructuredSummary,
    TemporaryFailureReply,
    ThreadMessage,
    ThreadMemoryState,
    TriggerCommand,
)
from app.services.analysis_service import AnalysisService
from app.services.command_parser import extract_approved_action_id
from app.services.incident_action_service import IncidentActionService
from app.services.kernel.interaction_recorder import InteractionRecorder
from app.services.kernel.memory_service import MemoryService
from app.services.knowledge_base import KnowledgeBase
from app.services.reply_renderer import ReplyRenderer
from app.services.skill_miner import SkillMiner
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
        incident_action_service: IncidentActionService | None = None,
        interaction_recorder: InteractionRecorder | None = None,
        skill_miner: SkillMiner | None = None,
    ) -> None:
        self.feishu_client = feishu_client
        self.thread_reader = thread_reader
        self.memory_service = memory_service
        self.knowledge_base = knowledge_base
        self.analysis_service = analysis_service
        self.reply_renderer = reply_renderer
        self.incident_action_service = incident_action_service
        self.interaction_recorder = interaction_recorder
        self.skill_miner = skill_miner

    async def process_trigger(
        self,
        *,
        trigger_command: TriggerCommand,
        trigger_event: NormalizedFeishuMessageEvent,
    ) -> None:
        if trigger_command is TriggerCommand.APPROVE_ACTION:
            await self._process_action_approval(trigger_event=trigger_event)
            return

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

        pending_actions = await self._prepare_pending_actions(
            trigger_event=trigger_event,
            trigger_command=trigger_command,
            analysis_request=analysis_request,
            reply_payload=reply_payload,
        )
        reply_text = self.reply_renderer.render_for_trigger(
            reply_payload,
            trigger_command=trigger_command,
        )
        if pending_actions and self.incident_action_service is not None:
            reply_text = f"{reply_text}\n\n{self.incident_action_service.render_pending_actions(pending_actions)}"

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
            if pending_actions and self.incident_action_service is not None:
                try:
                    scope = self.incident_action_service.action_queue_service.resolve_scope(trigger_event)
                    self.incident_action_service.discard_actions(
                        scope=scope,
                        actions=pending_actions,
                    )
                except Exception:
                    logger.exception(
                        "Failed to discard pending actions after reply send failure for thread_id=%s.",
                        analysis_request.thread_id,
                    )
            logger.warning(
                "Feishu reply send failed for thread_id=%s message_id=%s error=%s.",
                analysis_request.thread_id,
                analysis_request.trigger_message_id,
                send_result.error_message,
            )
            self._record_reply_send_failure(
                scope=self._resolve_record_scope(trigger_event),
                trigger_event=trigger_event,
                trigger_command=trigger_command,
                reply_payload=reply_payload,
                pending_actions=pending_actions,
                error_message=send_result.error_message,
            )
            return

        logger.info(
            "Feishu live flow completed for thread_id=%s trigger_message_id=%s reply_message_id=%s.",
            analysis_request.thread_id,
            analysis_request.trigger_message_id,
            send_result.reply_message_id,
        )
        self._record_analysis_events(
            scope=self._resolve_record_scope(trigger_event),
            analysis_request=analysis_request,
            trigger_command=trigger_command,
            reply_payload=reply_payload,
            reply_message_id=send_result.reply_message_id,
            pending_actions=pending_actions,
        )
        self._persist_thread_state(
            trigger_event=trigger_event,
            trigger_command=trigger_command,
            analysis_request=analysis_request,
            reply_payload=reply_payload,
            reply_text=reply_text,
            reply_message_id=send_result.reply_message_id,
        )

    async def _prepare_pending_actions(
        self,
        *,
        trigger_event: NormalizedFeishuMessageEvent,
        trigger_command: TriggerCommand,
        analysis_request: AnalysisRequest,
        reply_payload: StructuredSummary | TemporaryFailureReply,
    ) -> list[PendingIncidentAction]:
        if (
            self.incident_action_service is None
            or not isinstance(reply_payload, StructuredSummary)
            or not self.incident_action_service.should_prepare_actions(
                trigger_command=trigger_command,
                summary=reply_payload,
            )
        ):
            return []

        try:
            scope = self.incident_action_service.action_queue_service.resolve_scope(trigger_event)
            actions = await self.incident_action_service.prepare_actions(
                scope=scope,
                request=analysis_request,
                summary=reply_payload,
            )
            self.incident_action_service.persist_actions(
                scope=scope,
                actions=actions,
            )
            return actions
        except Exception:
            logger.exception(
                "Failed to prepare incident actions for thread_id=%s trigger_message_id=%s.",
                analysis_request.thread_id,
                analysis_request.trigger_message_id,
            )
            return []

    async def _process_action_approval(
        self,
        *,
        trigger_event: NormalizedFeishuMessageEvent,
    ) -> None:
        if self.incident_action_service is None:
            logger.warning("Approval command received without incident action service configured.")
            return

        action_id = extract_approved_action_id(trigger_event.message_text)
        if action_id is None:
            await self._send_action_reply(
                trigger_event=trigger_event,
                reply_text="未识别到动作编号。请使用“批准动作 A1”这类命令。",
            )
            return

        scope = self.incident_action_service.action_queue_service.resolve_scope(trigger_event)
        action = self.incident_action_service.action_queue_service.find_action(
            scope,
            action_id,
        )

        if action is not None and action.action_type is PendingActionType.POSTMORTEM_DRAFT:
            pending_action, reply_text = self.incident_action_service.build_postmortem_reply(
                scope=scope,
                action_id=action_id,
            )
            send_result = await self._send_action_reply(
                trigger_event=trigger_event,
                reply_text=reply_text,
            )
            if send_result.success and pending_action is not None:
                self.incident_action_service.mark_postmortem_action_executed(
                    scope=scope,
                    action=pending_action,
                    approved_by=trigger_event.sender_id,
                )
                updated_action = self.incident_action_service.action_queue_service.find_action(
                    scope,
                    action_id,
                )
                if updated_action is not None:
                    self._record_action_execution(
                        scope=scope,
                        trigger_event=trigger_event,
                        action=updated_action,
                    )
            elif not send_result.success:
                self._record_reply_send_failure(
                    scope=scope,
                    trigger_event=trigger_event,
                    trigger_command=TriggerCommand.APPROVE_ACTION,
                    reply_payload=None,
                    pending_actions=[],
                    error_message=send_result.error_message,
                    action_id=action_id,
                )
            return

        executed_action, reply_text = await self.incident_action_service.execute_task_sync_action(
            scope=scope,
            action_id=action_id,
            approved_by=trigger_event.sender_id,
        )
        send_result = await self._send_action_reply(
            trigger_event=trigger_event,
            reply_text=reply_text,
        )
        if send_result.success and executed_action is not None:
            self._record_action_execution(
                scope=scope,
                trigger_event=trigger_event,
                action=executed_action,
            )
        elif not send_result.success:
            self._record_reply_send_failure(
                scope=scope,
                trigger_event=trigger_event,
                trigger_command=TriggerCommand.APPROVE_ACTION,
                reply_payload=None,
                pending_actions=[],
                error_message=send_result.error_message,
                action_id=action_id,
            )

    async def _send_action_reply(
        self,
        *,
        trigger_event: NormalizedFeishuMessageEvent,
        reply_text: str,
    ):
        send_result = await self.feishu_client.reply_to_thread(
            chat_id=trigger_event.chat_id,
            thread_id=trigger_event.thread_id,
            trigger_message_id=trigger_event.message_id,
            reply_text=reply_text,
        )
        if not send_result.success:
            logger.warning(
                "Feishu action reply send failed for thread_id=%s message_id=%s error=%s.",
                trigger_event.thread_id,
                trigger_event.message_id,
                send_result.error_message,
            )
        return send_result

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

    def _record_analysis_events(
        self,
        *,
        scope: ActionScope,
        analysis_request: AnalysisRequest,
        trigger_command: TriggerCommand,
        reply_payload: StructuredSummary | TemporaryFailureReply,
        reply_message_id: str | None,
        pending_actions: list[PendingIncidentAction],
    ) -> None:
        if self.interaction_recorder is None:
            return

        analysis_record = InteractionRecord(
            event_id=self._build_event_id(
                trigger_message_id=analysis_request.trigger_message_id,
                suffix="analysis",
            ),
            correlation_key=self._build_correlation_key(
                event_type=InteractionEventType.ANALYSIS_REPLY_SENT,
                trigger_message_id=analysis_request.trigger_message_id,
                reply_message_id=reply_message_id,
            ),
            event_type=InteractionEventType.ANALYSIS_REPLY_SENT,
            tenant_id=scope.tenant_id,
            thread_id=scope.thread_id,
            actor_id=analysis_request.user_id,
            occurred_at=datetime.now(timezone.utc),
            trigger_command=trigger_command,
            summary_status=getattr(reply_payload, "status", None),
            payload=self._build_analysis_payload(reply_payload, pending_actions),
        )
        self.interaction_recorder.record(scope, analysis_record)

        if not pending_actions:
            return

        proposal_record = InteractionRecord(
            event_id=self._build_event_id(
                trigger_message_id=analysis_request.trigger_message_id,
                suffix="actions",
            ),
            correlation_key=self._build_correlation_key(
                event_type=InteractionEventType.ACTIONS_PROPOSED,
                trigger_message_id=analysis_request.trigger_message_id,
                action_id="-".join(action.action_id for action in pending_actions),
            ),
            event_type=InteractionEventType.ACTIONS_PROPOSED,
            tenant_id=scope.tenant_id,
            thread_id=scope.thread_id,
            actor_id=analysis_request.user_id,
            occurred_at=datetime.now(timezone.utc),
            trigger_command=trigger_command,
            summary_status=getattr(reply_payload, "status", None),
            payload={
                "action_count": len(pending_actions),
                "action_refs": [
                    {
                        "action_id": action.action_id,
                        "action_type": action.action_type.value,
                        "status": action.status.value,
                    }
                    for action in pending_actions
                ],
            },
        )
        self.interaction_recorder.record(scope, proposal_record)

    def _record_action_execution(
        self,
        *,
        scope: ActionScope,
        trigger_event: NormalizedFeishuMessageEvent,
        action: PendingIncidentAction,
    ) -> None:
        if self.interaction_recorder is None:
            return

        record = InteractionRecord(
            event_id=self._build_event_id(
                trigger_message_id=trigger_event.message_id,
                suffix=f"action-{action.action_id.lower()}",
            ),
            correlation_key=self._build_correlation_key(
                event_type=InteractionEventType.ACTION_EXECUTED,
                trigger_message_id=trigger_event.message_id,
                action_id=action.action_id,
            ),
            event_type=InteractionEventType.ACTION_EXECUTED,
            tenant_id=scope.tenant_id,
            thread_id=scope.thread_id,
            actor_id=trigger_event.sender_id,
            occurred_at=datetime.now(timezone.utc),
            trigger_command=TriggerCommand.APPROVE_ACTION,
            action_id=action.action_id,
            action_type=action.action_type,
            pattern_key=self._pattern_key_for(action.action_type),
            payload={
                "execution_status": (
                    "executed"
                    if action.status.value == "executed"
                    else "execution_failed"
                ),
                "execution_message": action.execution_message or "",
                "action_title": action.title,
            },
        )
        self.interaction_recorder.record(scope, record)

        if (
            self.skill_miner is not None
            and action.status.value == "executed"
        ):
            self.skill_miner.evaluate_tenant(scope.tenant_id)

    def _record_reply_send_failure(
        self,
        *,
        scope: ActionScope,
        trigger_event: NormalizedFeishuMessageEvent,
        trigger_command: TriggerCommand,
        reply_payload: StructuredSummary | TemporaryFailureReply | None,
        pending_actions: list[PendingIncidentAction],
        error_message: str | None,
        action_id: str | None = None,
    ) -> None:
        if self.interaction_recorder is None:
            return

        record = InteractionRecord(
            event_id=self._build_event_id(
                trigger_message_id=trigger_event.message_id,
                suffix="reply-failed",
            ),
            correlation_key=self._build_correlation_key(
                event_type=InteractionEventType.REPLY_SEND_FAILED,
                trigger_message_id=trigger_event.message_id,
                action_id=action_id,
            ),
            event_type=InteractionEventType.REPLY_SEND_FAILED,
            tenant_id=scope.tenant_id,
            thread_id=scope.thread_id,
            actor_id=trigger_event.sender_id,
            occurred_at=datetime.now(timezone.utc),
            trigger_command=trigger_command,
            summary_status=getattr(reply_payload, "status", None),
            action_id=action_id,
            payload={
                "error_message": error_message or "unknown_reply_send_failure",
                "pending_action_ids": [action.action_id for action in pending_actions],
            },
        )
        self.interaction_recorder.record(scope, record)

    def _build_analysis_payload(
        self,
        reply_payload: StructuredSummary | TemporaryFailureReply,
        pending_actions: list[PendingIncidentAction],
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "headline": getattr(reply_payload, "current_assessment", None)
            or getattr(reply_payload, "headline", None)
            or "",
            "known_facts": reply_payload.known_facts[:3],
            "missing_information": reply_payload.missing_information[:3],
            "citation_refs": [
                {
                    "label": citation.label,
                    "source_uri": citation.source_uri,
                }
                for citation in reply_payload.citations[:3]
            ],
            "pending_action_refs": [
                {
                    "action_id": action.action_id,
                    "action_type": action.action_type.value,
                    "status": action.status.value,
                }
                for action in pending_actions
            ],
        }
        if isinstance(reply_payload, StructuredSummary):
            payload["conclusion_summary"] = reply_payload.conclusion_summary or ""
        return payload

    def _resolve_record_scope(self, trigger_event: NormalizedFeishuMessageEvent) -> ActionScope:
        if self.incident_action_service is not None:
            return self.incident_action_service.action_queue_service.resolve_scope(trigger_event)
        return ActionScope(
            tenant_id=trigger_event.chat_id,
            thread_id=trigger_event.thread_id,
        )

    def _build_event_id(self, *, trigger_message_id: str, suffix: str) -> str:
        return f"{trigger_message_id}-{suffix}"

    def _build_correlation_key(
        self,
        *,
        event_type: InteractionEventType,
        trigger_message_id: str,
        reply_message_id: str | None = None,
        action_id: str | None = None,
    ) -> str:
        parts = [event_type.value, trigger_message_id]
        if reply_message_id:
            parts.append(reply_message_id)
        if action_id:
            parts.append(action_id)
        return ":".join(parts)

    def _pattern_key_for(self, action_type: PendingActionType) -> str:
        return f"incident/{action_type.value}/approval_loop"
