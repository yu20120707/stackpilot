from __future__ import annotations

from datetime import datetime, timezone

from app.models.contracts import (
    ActionScope,
    AnalysisRequest,
    AnalysisResultStatus,
    ExternalTaskTarget,
    OrgPostmortemStyle,
    PendingActionStatus,
    PendingActionType,
    PendingIncidentAction,
    PostmortemDraft,
    StructuredSummary,
    TaskSyncStatus,
    TriggerCommand,
)
from app.services.kernel.action_queue_service import ActionQueueService
from app.services.kernel.org_convention_service import OrgConventionService
from app.services.incident.postmortem_renderer import PostmortemRenderer
from app.services.incident.postmortem_service import PostmortemService
from app.services.incident.task_sync_service import TaskSyncService


class IncidentActionService:
    def __init__(
        self,
        *,
        action_queue_service: ActionQueueService,
        task_sync_service: TaskSyncService,
        postmortem_service: PostmortemService,
        postmortem_renderer: PostmortemRenderer,
        org_convention_service: OrgConventionService | None = None,
    ) -> None:
        self.action_queue_service = action_queue_service
        self.task_sync_service = task_sync_service
        self.postmortem_service = postmortem_service
        self.postmortem_renderer = postmortem_renderer
        self.org_convention_service = org_convention_service

    def should_prepare_actions(
        self,
        *,
        trigger_command: TriggerCommand,
        summary: StructuredSummary,
    ) -> bool:
        return (
            trigger_command is TriggerCommand.SUMMARIZE_THREAD
            and summary.status is AnalysisResultStatus.SUCCESS
        )

    async def prepare_actions(
        self,
        *,
        scope: ActionScope,
        request: AnalysisRequest,
        summary: StructuredSummary,
    ) -> list[PendingIncidentAction]:
        now = datetime.now(timezone.utc)
        action_ids = self._allocate_action_ids(scope, count=2)
        postmortem_style = self._load_postmortem_style(scope)

        task_sync_request = self.task_sync_service.build_sync_request_from_summary(
            summary,
            source_thread_id=request.thread_id,
            requested_by=request.user_id,
            target=ExternalTaskTarget.GENERIC,
        )
        task_action = PendingIncidentAction(
            action_id=action_ids[0],
            action_type=PendingActionType.TASK_SYNC,
            status=PendingActionStatus.PENDING_APPROVAL,
            title="同步待办草稿",
            preview=self._build_task_action_preview(task_sync_request.task_drafts),
            source_thread_id=request.thread_id,
            created_by=request.user_id,
            created_at=now,
            updated_at=now,
            task_sync_request=task_sync_request,
        )

        postmortem_draft = await self.postmortem_service.generate_draft(
            request=request,
            summary=summary,
            org_style=postmortem_style,
        )
        postmortem_action = PendingIncidentAction(
            action_id=action_ids[1],
            action_type=PendingActionType.POSTMORTEM_DRAFT,
            status=PendingActionStatus.PENDING_APPROVAL,
            title="回写复盘草稿",
            preview=self._build_postmortem_preview(postmortem_draft),
            source_thread_id=request.thread_id,
            created_by=request.user_id,
            created_at=now,
            updated_at=now,
            postmortem_draft=postmortem_draft,
            postmortem_style_snapshot=postmortem_style,
        )
        return [task_action, postmortem_action]

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
        self.action_queue_service.remove_actions(
            scope,
            [action.action_id for action in actions],
        )

    def render_pending_actions(self, actions: list[PendingIncidentAction]) -> str:
        if not actions:
            return ""

        lines = ["待审批动作："]
        for action in actions:
            lines.append(f"- [{action.action_id}] {action.title}")
            lines.append(f"  {action.preview}")
            lines.append(f"  批准命令：批准动作 {action.action_id}")
        return "\n".join(lines)

    async def execute_task_sync_action(
        self,
        *,
        scope: ActionScope,
        action_id: str,
        approved_by: str,
    ) -> tuple[PendingIncidentAction | None, str]:
        action = self.action_queue_service.find_action(scope, action_id)
        if action is None:
            return None, self._render_missing_action(action_id)
        if action.status is not PendingActionStatus.PENDING_APPROVAL:
            return None, self._render_existing_action_result(action)
        if action.action_type is not PendingActionType.TASK_SYNC or action.task_sync_request is None:
            return None, f"动作 {action.action_id} 不是可执行的任务同步动作。"

        confirmed_request = action.task_sync_request.model_copy(
            update={"confirmed": True}
        )
        result = await self.task_sync_service.sync_prepared_tasks(confirmed_request)
        now = datetime.now(timezone.utc)
        updated_action = action.model_copy(
            update={
                "status": (
                    PendingActionStatus.EXECUTED
                    if result.status is TaskSyncStatus.SYNCED
                    else PendingActionStatus.EXECUTION_FAILED
                ),
                "task_sync_request": confirmed_request,
                "approved_by": approved_by,
                "approved_at": now,
                "updated_at": now,
                "execution_message": result.message,
            }
        )
        self.action_queue_service.update_action(scope, updated_action)
        return updated_action, self._render_task_sync_result(updated_action, result)

    def build_postmortem_reply(
        self,
        *,
        scope: ActionScope,
        action_id: str,
    ) -> tuple[PendingIncidentAction | None, str]:
        action = self.action_queue_service.find_action(scope, action_id)
        if action is None:
            return None, self._render_missing_action(action_id)
        if action.status is not PendingActionStatus.PENDING_APPROVAL:
            return None, self._render_existing_action_result(action)
        if action.action_type is not PendingActionType.POSTMORTEM_DRAFT or action.postmortem_draft is None:
            return None, f"动作 {action.action_id} 不是可回写的复盘动作。"

        rendered_draft = self.postmortem_renderer.render(
            action.postmortem_draft,
            org_style=action.postmortem_style_snapshot or self._load_postmortem_style(scope),
        )
        return action, f"动作执行结果：\n已回写复盘草稿 {action.action_id}。\n\n{rendered_draft}"

    def mark_postmortem_action_executed(
        self,
        *,
        scope: ActionScope,
        action: PendingIncidentAction,
        approved_by: str,
    ) -> None:
        now = datetime.now(timezone.utc)
        updated_action = action.model_copy(
            update={
                "status": PendingActionStatus.EXECUTED,
                "approved_by": approved_by,
                "approved_at": now,
                "updated_at": now,
                "execution_message": "postmortem_draft_written_back",
            }
        )
        self.action_queue_service.update_action(scope, updated_action)

    def _allocate_action_ids(
        self,
        scope: ActionScope,
        *,
        count: int,
    ) -> list[str]:
        next_index = 1
        for action in self.action_queue_service.load_state(scope).actions:
            if not action.action_id.startswith("A"):
                continue
            raw_index = action.action_id[1:]
            if raw_index.isdigit():
                next_index = max(next_index, int(raw_index) + 1)

        action_ids: list[str] = []
        for _ in range(count):
            action_ids.append(f"A{next_index}")
            next_index += 1
        return action_ids

    def _build_task_action_preview(self, task_drafts: list) -> str:
        preview_titles = [draft.title for draft in task_drafts[:2]]
        preview_suffix = "；".join(preview_titles)
        if len(task_drafts) > 2:
            preview_suffix = f"{preview_suffix}；等 {len(task_drafts)} 项"
        return f"将同步 {len(task_drafts)} 个待办草稿。预览：{preview_suffix}"

    def _build_postmortem_preview(self, draft: PostmortemDraft) -> str:
        return (
            f"复盘标题：{draft.title}；"
            f"时间线 {len(draft.timeline)} 条；"
            f"后续动作 {len(draft.follow_up_actions)} 项"
        )

    def _render_missing_action(self, action_id: str) -> str:
        return f"未找到待审批动作：{action_id.upper()}。请确认动作编号是否来自当前线程。"

    def _render_existing_action_result(self, action: PendingIncidentAction) -> str:
        if action.status is PendingActionStatus.EXECUTED:
            suffix = action.execution_message or "already_executed"
            return f"动作 {action.action_id} 已执行，无需重复批准。({suffix})"
        suffix = action.execution_message or "execution_failed"
        return f"动作 {action.action_id} 上次执行失败，可重新生成新的动作草稿。({suffix})"

    def _render_task_sync_result(self, action: PendingIncidentAction, result) -> str:  # noqa: ANN001
        lines = [f"动作执行结果：{action.action_id} {action.title}"]
        if result.status is TaskSyncStatus.SYNCED:
            lines.append(f"- 已同步 {len(result.synced_tasks)} 个外部任务")
            for synced_task in result.synced_tasks:
                task_ref = synced_task.external_url or synced_task.external_id
                lines.append(f"- {synced_task.title} -> {task_ref}")
        else:
            lines.append(f"- 执行失败：{result.message}")
        return "\n".join(lines)

    def _load_postmortem_style(self, scope: ActionScope) -> OrgPostmortemStyle | None:
        if self.org_convention_service is None:
            return None
        return self.org_convention_service.load_postmortem_style(scope.tenant_id)
