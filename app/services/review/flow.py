from __future__ import annotations

from datetime import datetime, timezone

from app.clients.feishu_client import FeishuClient
from app.clients.github_review_client import GitHubReviewClient
from app.core.logging import get_logger
from app.models.contracts import (
    ActionScope,
    CodeReviewDraft,
    CodeReviewRequest,
    InteractionEventType,
    InteractionRecord,
    NormalizedFeishuMessageEvent,
    PendingActionType,
    PendingIncidentAction,
    ReviewFeedbackStatus,
    ReviewFocusArea,
    ReviewMemoryState,
    TriggerCommand,
)
from app.services.command_parser import extract_approved_action_id, extract_review_feedback
from app.services.kernel.interaction_recorder import InteractionRecorder
from app.services.kernel.memory_service import MemoryService
from app.services.review.diff_reader import DiffReader
from app.services.review.input_parser import extract_review_input
from app.services.review.preference_service import ReviewPreferenceService
from app.services.review.policy_service import ReviewPolicyService
from app.services.review.publish_service import ReviewPublishService
from app.services.review.renderer import ReviewRenderer
from app.services.review.service import ReviewService
from app.services.skill_miner import SkillMiner


logger = get_logger(__name__)


class CodeReviewFlow:
    def __init__(
        self,
        *,
        feishu_client: FeishuClient,
        github_review_client: GitHubReviewClient,
        diff_reader: DiffReader,
        review_policy_service: ReviewPolicyService,
        review_preference_service: ReviewPreferenceService,
        review_service: ReviewService,
        review_renderer: ReviewRenderer,
        review_publish_service: ReviewPublishService,
        memory_service: MemoryService | None = None,
        interaction_recorder: InteractionRecorder | None = None,
        skill_miner: SkillMiner | None = None,
    ) -> None:
        self.feishu_client = feishu_client
        self.github_review_client = github_review_client
        self.diff_reader = diff_reader
        self.review_policy_service = review_policy_service
        self.review_preference_service = review_preference_service
        self.review_service = review_service
        self.review_renderer = review_renderer
        self.review_publish_service = review_publish_service
        self.memory_service = memory_service
        self.interaction_recorder = interaction_recorder
        self.skill_miner = skill_miner

    async def process_trigger(
        self,
        *,
        trigger_command: TriggerCommand,
        trigger_event: NormalizedFeishuMessageEvent,
    ) -> None:
        review_request = await self._build_review_request(
            trigger_command=trigger_command,
            trigger_event=trigger_event,
        )
        if review_request is None:
            await self._send_reply(
                trigger_event=trigger_event,
                reply_text="未识别到可审查的 PR 链接或 diff/patch。请直接贴 GitHub PR 链接，或粘贴 diff/patch 后再触发。",
            )
            return

        policy_citations = self.review_policy_service.retrieve_policy_citations(review_request)
        review_request = review_request.model_copy(update={"policy_citations": policy_citations})
        review_reply = await self.review_service.review(review_request)

        pending_actions = await self._prepare_pending_actions(
            trigger_event=trigger_event,
            review_request=review_request,
            review_reply=review_reply,
        )
        reply_text = self.review_renderer.render(review_reply)
        if pending_actions:
            reply_text = f"{reply_text}\n\n{self.review_renderer.render_pending_actions(pending_actions)}"

        send_result = await self._send_reply(
            trigger_event=trigger_event,
            reply_text=reply_text,
        )
        scope = self.review_publish_service.action_queue_service.resolve_scope(trigger_event)
        if not send_result.success:
            if pending_actions:
                self.review_publish_service.discard_actions(
                    scope=scope,
                    actions=pending_actions,
                )
            self._record_reply_send_failure(
                scope=scope,
                trigger_event=trigger_event,
                action_id=None,
            )
            return

        self._record_review_events(
            scope=scope,
            trigger_event=trigger_event,
            review_request=review_request,
            review_reply=review_reply,
            pending_actions=pending_actions,
        )
        self._persist_review_state(
            trigger_event=trigger_event,
            review_request=review_request,
            review_reply=review_reply,
            pending_actions=pending_actions,
            reply_message_id=send_result.reply_message_id,
        )

    async def process_approval(
        self,
        *,
        trigger_event: NormalizedFeishuMessageEvent,
    ) -> bool:
        action_id = extract_approved_action_id(trigger_event.message_text)
        if action_id is None:
            return False

        scope = self.review_publish_service.action_queue_service.resolve_scope(trigger_event)
        if not self.review_publish_service.can_handle_action(scope, action_id):
            return False

        executed_action, reply_text = await self.review_publish_service.execute_publish_action(
            scope=scope,
            action_id=action_id,
            approved_by=trigger_event.sender_id,
        )
        send_result = await self._send_reply(
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
                action_id=action_id,
            )
        return True

    async def process_feedback(
        self,
        *,
        trigger_event: NormalizedFeishuMessageEvent,
    ) -> bool:
        feedback = extract_review_feedback(trigger_event.message_text)
        if feedback is None:
            return False
        if self.memory_service is None:
            return False

        memory_scope = self.memory_service.resolve_scope(trigger_event)
        review_state = self.memory_service.load_review_state(memory_scope)
        if review_state is None:
            await self._send_reply(
                trigger_event=trigger_event,
                reply_text="当前线程里还没有可记录反馈的 review 草稿。请先触发一次代码审查。",
            )
            return True

        status_name, finding_id = feedback
        feedback_status = (
            ReviewFeedbackStatus.ACCEPTED
            if status_name == "accepted"
            else ReviewFeedbackStatus.IGNORED
        )

        updated_findings = []
        target_finding = None
        now = datetime.now(timezone.utc)
        for finding in review_state.findings:
            if (finding.finding_id or "").upper() == finding_id:
                updated_finding = finding.model_copy(
                    update={
                        "feedback_status": feedback_status,
                        "feedback_recorded_at": now,
                    }
                )
                updated_findings.append(updated_finding)
                target_finding = updated_finding
            else:
                updated_findings.append(finding)

        if target_finding is None:
            await self._send_reply(
                trigger_event=trigger_event,
                reply_text=f"未找到 review finding：{finding_id}。请确认编号来自当前线程里的代码审查结果。",
            )
            return True

        next_state = review_state.model_copy(
            update={
                "findings": updated_findings,
                "updated_at": now,
            }
        )
        self.memory_service.save_review_state(memory_scope, next_state)

        scope = self.review_publish_service.action_queue_service.resolve_scope(trigger_event)
        self._record_review_feedback(
            scope=scope,
            trigger_event=trigger_event,
            finding=target_finding,
            feedback_status=feedback_status,
            source_ref=review_state.source_ref,
        )
        self.review_preference_service.observe_feedback(
            scope=memory_scope,
            finding=target_finding,
            feedback_status=feedback_status,
        )
        if self.skill_miner is not None:
            self.skill_miner.evaluate_tenant(scope.tenant_id)

        feedback_text = "已记录为采纳" if feedback_status is ReviewFeedbackStatus.ACCEPTED else "已记录为忽略"
        await self._send_reply(
            trigger_event=trigger_event,
            reply_text=f"{feedback_text}：{target_finding.finding_id} {target_finding.title}",
        )
        return True

    async def _build_review_request(
        self,
        *,
        trigger_command: TriggerCommand,
        trigger_event: NormalizedFeishuMessageEvent,
    ) -> CodeReviewRequest | None:
        review_input = extract_review_input(trigger_event.message_text)
        if review_input is None:
            return None

        if self.memory_service is not None:
            memory_scope = self.memory_service.resolve_scope(trigger_event)
            focus_areas, explicit_focus_areas = self.review_preference_service.resolve_focus_areas(
                scope=memory_scope,
                message_text=trigger_event.message_text,
            )
            self.review_preference_service.observe_review_request(
                scope=memory_scope,
                explicit_focus_areas=explicit_focus_areas,
            )
        else:
            focus_areas = self.review_preference_service.extract_focus_areas(trigger_event.message_text)
            if not focus_areas:
                focus_areas = [ReviewFocusArea.BUG_RISK, ReviewFocusArea.TEST_GAP]

        normalized_patch = review_input.raw_input
        if review_input.source_type.value == "github_pr":
            try:
                fetched_patch = await self.github_review_client.fetch_pull_request_diff(review_input.source_ref)
            except Exception:
                logger.exception(
                    "Failed to fetch GitHub PR diff for source_ref=%s message_id=%s.",
                    review_input.source_ref,
                    trigger_event.message_id,
                )
                fetched_patch = None
            normalized_patch = fetched_patch or "patch_fetch_failed"

        files = self.diff_reader.parse(normalized_patch) if normalized_patch != "patch_fetch_failed" else []
        return CodeReviewRequest(
            trigger_command=trigger_command,
            chat_id=trigger_event.chat_id,
            thread_id=trigger_event.thread_id,
            trigger_message_id=trigger_event.message_id,
            user_id=trigger_event.sender_id,
            user_display_name=trigger_event.sender_name,
            source_type=review_input.source_type,
            source_ref=review_input.source_ref,
            raw_input=review_input.raw_input,
            normalized_patch=normalized_patch,
            files=files,
            focus_areas=focus_areas,
            source_message_text=trigger_event.message_text,
        )

    async def _prepare_pending_actions(
        self,
        *,
        trigger_event: NormalizedFeishuMessageEvent,
        review_request: CodeReviewRequest,
        review_reply,
    ) -> list[PendingIncidentAction]:
        if not isinstance(review_reply, CodeReviewDraft):
            return []
        if not self.review_publish_service.should_prepare_publish_action(
            request=review_request,
            review_draft=review_reply,
        ):
            return []

        scope = self.review_publish_service.action_queue_service.resolve_scope(trigger_event)
        action = self.review_publish_service.prepare_publish_action(
            scope=scope,
            request=review_request,
            review_draft=review_reply,
        )
        return self.review_publish_service.persist_actions(scope=scope, actions=[action])

    async def _send_reply(
        self,
        *,
        trigger_event: NormalizedFeishuMessageEvent,
        reply_text: str,
    ):
        return await self.feishu_client.reply_to_thread(
            chat_id=trigger_event.chat_id,
            thread_id=trigger_event.thread_id,
            trigger_message_id=trigger_event.message_id,
            reply_text=reply_text,
        )

    def _record_review_events(
        self,
        *,
        scope: ActionScope,
        trigger_event: NormalizedFeishuMessageEvent,
        review_request: CodeReviewRequest,
        review_reply,
        pending_actions: list[PendingIncidentAction],
    ) -> None:
        if self.interaction_recorder is None:
            return

        review_record = InteractionRecord(
            event_id=f"{trigger_event.message_id}-review",
            correlation_key=f"{InteractionEventType.REVIEW_DRAFT_SENT.value}:{trigger_event.message_id}:{review_request.source_ref}",
            event_type=InteractionEventType.REVIEW_DRAFT_SENT,
            tenant_id=scope.tenant_id,
            thread_id=scope.thread_id,
            actor_id=trigger_event.sender_id,
            occurred_at=datetime.now(timezone.utc),
            trigger_command=TriggerCommand.REVIEW_CODE,
            payload={
                "source_ref": review_request.source_ref,
                "source_type": review_request.source_type.value,
                "focus_areas": [item.value for item in review_request.focus_areas],
                "changed_files": len(review_request.files),
                "policy_refs": [citation.source_uri for citation in review_request.policy_citations],
                "status": getattr(review_reply, "status", None),
                "finding_count": len(getattr(review_reply, "findings", [])),
            },
        )
        self.interaction_recorder.record(scope, review_record)

        if not pending_actions:
            return

        proposal_record = InteractionRecord(
            event_id=f"{trigger_event.message_id}-review-actions",
            correlation_key=f"{InteractionEventType.ACTIONS_PROPOSED.value}:{trigger_event.message_id}:{'-'.join(action.action_id for action in pending_actions)}",
            event_type=InteractionEventType.ACTIONS_PROPOSED,
            tenant_id=scope.tenant_id,
            thread_id=scope.thread_id,
            actor_id=trigger_event.sender_id,
            occurred_at=datetime.now(timezone.utc),
            trigger_command=TriggerCommand.REVIEW_CODE,
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
            event_id=f"{trigger_event.message_id}-action-{action.action_id.lower()}",
            correlation_key=f"{InteractionEventType.ACTION_EXECUTED.value}:{trigger_event.message_id}:{action.action_id}",
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

        if self.skill_miner is not None and action.status.value == "executed":
            self.skill_miner.evaluate_tenant(scope.tenant_id)

    def _record_review_feedback(
        self,
        *,
        scope: ActionScope,
        trigger_event: NormalizedFeishuMessageEvent,
        finding,
        feedback_status: ReviewFeedbackStatus,
        source_ref: str,
    ) -> None:
        if self.interaction_recorder is None:
            return

        primary_focus = finding.focus_areas[0].value if finding.focus_areas else "general"
        record = InteractionRecord(
            event_id=f"{trigger_event.message_id}-feedback-{(finding.finding_id or 'finding').lower()}",
            correlation_key=f"{InteractionEventType.REVIEW_FEEDBACK_RECORDED.value}:{trigger_event.message_id}:{finding.finding_id}:{feedback_status.value}",
            event_type=InteractionEventType.REVIEW_FEEDBACK_RECORDED,
            tenant_id=scope.tenant_id,
            thread_id=scope.thread_id,
            actor_id=trigger_event.sender_id,
            occurred_at=datetime.now(timezone.utc),
            trigger_command=TriggerCommand.REVIEW_FEEDBACK,
            pattern_key=f"review/focus/{primary_focus}/{feedback_status.value}_finding",
            payload={
                "finding_id": finding.finding_id,
                "finding_title": finding.title,
                "focus_areas": [item.value for item in finding.focus_areas],
                "feedback_status": feedback_status.value,
                "source_ref": source_ref,
            },
        )
        self.interaction_recorder.record(scope, record)

    def _record_reply_send_failure(
        self,
        *,
        scope: ActionScope,
        trigger_event: NormalizedFeishuMessageEvent,
        action_id: str | None,
    ) -> None:
        if self.interaction_recorder is None:
            return

        record = InteractionRecord(
            event_id=f"{trigger_event.message_id}-review-reply-failed",
            correlation_key=f"{InteractionEventType.REPLY_SEND_FAILED.value}:{trigger_event.message_id}:{action_id or 'review'}",
            event_type=InteractionEventType.REPLY_SEND_FAILED,
            tenant_id=scope.tenant_id,
            thread_id=scope.thread_id,
            actor_id=trigger_event.sender_id,
            occurred_at=datetime.now(timezone.utc),
            trigger_command=(
                TriggerCommand.APPROVE_ACTION if action_id else TriggerCommand.REVIEW_CODE
            ),
            action_id=action_id,
            payload={"error_message": "feishu_send_failed"},
        )
        self.interaction_recorder.record(scope, record)

    def _persist_review_state(
        self,
        *,
        trigger_event: NormalizedFeishuMessageEvent,
        review_request: CodeReviewRequest,
        review_reply,
        pending_actions: list[PendingIncidentAction],
        reply_message_id: str | None,
    ) -> None:
        if self.memory_service is None or not isinstance(review_reply, CodeReviewDraft):
            return

        scope = self.memory_service.resolve_scope(trigger_event)
        review_state = ReviewMemoryState(
            source_type=review_request.source_type,
            source_ref=review_request.source_ref,
            last_review_message_id=reply_message_id,
            last_review_status=review_reply.status,
            focus_areas=review_request.focus_areas,
            findings=review_reply.findings,
            updated_at=datetime.now(timezone.utc),
        )
        self.memory_service.save_review_state(scope, review_state)

    def _pattern_key_for(self, action_type: PendingActionType) -> str:
        return f"review/{action_type.value}/approval_loop"
