from __future__ import annotations

from datetime import datetime, timezone

from app.clients.github_review_client import GitHubReviewClient
from app.models.contracts import (
    ActionScope,
    CodeReviewDraft,
    CodeReviewRequest,
    PendingActionStatus,
    PendingActionType,
    PendingIncidentAction,
    ReviewPublishRequest,
    ReviewPublishResult,
    ReviewPublishStatus,
)
from app.services.kernel.action_queue_service import ActionQueueService
from app.services.review.renderer import ReviewRenderer


class ReviewPublishService:
    def __init__(
        self,
        *,
        action_queue_service: ActionQueueService,
        github_review_client: GitHubReviewClient,
        review_renderer: ReviewRenderer,
    ) -> None:
        self.action_queue_service = action_queue_service
        self.github_review_client = github_review_client
        self.review_renderer = review_renderer

    def should_prepare_publish_action(
        self,
        *,
        request: CodeReviewRequest,
        review_draft: CodeReviewDraft,
    ) -> bool:
        return request.source_type.value == "github_pr" and review_draft.status.value == "success"

    def prepare_publish_action(
        self,
        *,
        scope: ActionScope,
        request: CodeReviewRequest,
        review_draft: CodeReviewDraft,
    ) -> PendingIncidentAction:
        now = datetime.now(timezone.utc)
        action_id = self._allocate_action_id(scope)
        comment_body = self.review_renderer.render_publish_comment(review_draft)
        publish_request = ReviewPublishRequest(
            source_type=request.source_type,
            source_ref=request.source_ref,
            requested_by=request.user_id,
            comment_body=comment_body,
            require_confirmation=True,
            confirmed=False,
        )
        return PendingIncidentAction(
            action_id=action_id,
            action_type=PendingActionType.REVIEW_PUBLISH,
            status=PendingActionStatus.PENDING_APPROVAL,
            title="发布 GitHub CR 草稿",
            preview=self._build_publish_preview(request, review_draft),
            source_thread_id=request.thread_id,
            created_by=request.user_id,
            created_at=now,
            updated_at=now,
            review_publish_request=publish_request,
            review_draft=review_draft,
        )

    def persist_actions(
        self,
        *,
        scope: ActionScope,
        actions: list[PendingIncidentAction],
    ) -> list[PendingIncidentAction]:
        return self.action_queue_service.enqueue_actions(scope, actions)

    def discard_actions(
        self,
        *,
        scope: ActionScope,
        actions: list[PendingIncidentAction],
    ) -> None:
        self.action_queue_service.remove_actions(scope, [action.action_id for action in actions])

    def can_handle_action(self, scope: ActionScope, action_id: str) -> bool:
        action = self.action_queue_service.find_action(scope, action_id)
        return action is not None and action.action_type is PendingActionType.REVIEW_PUBLISH

    async def execute_publish_action(
        self,
        *,
        scope: ActionScope,
        action_id: str,
        approved_by: str,
    ) -> tuple[PendingIncidentAction | None, str]:
        action = self.action_queue_service.find_action(scope, action_id)
        if action is None:
            return None, self._render_missing_action(action_id)
        if action.action_type is not PendingActionType.REVIEW_PUBLISH or action.review_publish_request is None:
            return None, f"动作 {action.action_id} 不是可发布的代码审查动作。"
        if action.status is not PendingActionStatus.PENDING_APPROVAL:
            return None, self._render_existing_action_result(action)

        publish_request = action.review_publish_request.model_copy(update={"confirmed": True})
        published_ref = await self.github_review_client.publish_issue_comment(
            pull_request_url=publish_request.source_ref,
            body=publish_request.comment_body,
        )
        result = self._build_publish_result(
            request=publish_request,
            published_ref=published_ref,
        )
        now = datetime.now(timezone.utc)
        updated_action = action.model_copy(
            update={
                "status": (
                    PendingActionStatus.EXECUTED
                    if result.status is ReviewPublishStatus.PUBLISHED
                    else PendingActionStatus.EXECUTION_FAILED
                ),
                "approved_by": approved_by,
                "approved_at": now,
                "updated_at": now,
                "execution_message": result.message,
                "review_publish_request": publish_request,
            }
        )
        self.action_queue_service.update_action(scope, updated_action)
        return updated_action, self._render_publish_result(updated_action, result)

    def _allocate_action_id(self, scope: ActionScope) -> str:
        next_index = 1
        for action in self.action_queue_service.load_state(scope).actions:
            if not action.action_id.startswith("R"):
                continue
            raw_index = action.action_id[1:]
            if raw_index.isdigit():
                next_index = max(next_index, int(raw_index) + 1)
        return f"R{next_index}"

    def _build_publish_preview(
        self,
        request: CodeReviewRequest,
        review_draft: CodeReviewDraft,
    ) -> str:
        return (
            f"将向 {request.source_ref} 发布 1 条 draft review comment，"
            f"包含 {len(review_draft.findings)} 条 finding。"
        )

    def _build_publish_result(
        self,
        *,
        request: ReviewPublishRequest,
        published_ref: str | None,
    ) -> ReviewPublishResult:
        if published_ref is None:
            return ReviewPublishResult(
                status=ReviewPublishStatus.PUBLISH_FAILED,
                source_ref=request.source_ref,
                message="github_review_publish_failed",
            )

        return ReviewPublishResult(
            status=ReviewPublishStatus.PUBLISHED,
            source_ref=request.source_ref,
            message="github_review_published",
            published_ref=published_ref,
        )

    def _render_missing_action(self, action_id: str) -> str:
        return f"未找到待审批动作：{action_id.upper()}。请确认动作编号是否来自当前线程。"

    def _render_existing_action_result(self, action: PendingIncidentAction) -> str:
        if action.status is PendingActionStatus.EXECUTED:
            suffix = action.execution_message or "already_executed"
            return f"动作 {action.action_id} 已执行，无需重复批准。({suffix})"
        suffix = action.execution_message or "execution_failed"
        return f"动作 {action.action_id} 上次执行失败，可重新生成新的 review 草稿。({suffix})"

    def _render_publish_result(
        self,
        action: PendingIncidentAction,
        result: ReviewPublishResult,
    ) -> str:
        lines = [f"动作执行结果：{action.action_id} {action.title}"]
        if result.status is ReviewPublishStatus.PUBLISHED:
            lines.append(f"- 已发布到 GitHub：{result.published_ref}")
        else:
            lines.append(f"- 发布失败：{result.message}")
        return "\n".join(lines)
