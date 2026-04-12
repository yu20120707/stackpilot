from __future__ import annotations

from app.clients.task_sync_client import TaskSyncClient
from app.models.contracts import (
    ExternalTaskDraft,
    ExternalTaskSyncRequest,
    ExternalTaskSyncResult,
    ExternalTaskTarget,
    StructuredSummary,
    SyncedExternalTask,
    TaskSyncStatus,
)


class TaskSyncService:
    def __init__(self, task_sync_client: TaskSyncClient | None = None) -> None:
        self.task_sync_client = task_sync_client

    def build_sync_request_from_summary(
        self,
        summary: StructuredSummary,
        *,
        source_thread_id: str,
        requested_by: str,
        target: ExternalTaskTarget = ExternalTaskTarget.GENERIC,
        confirmed: bool = False,
    ) -> ExternalTaskSyncRequest:
        task_drafts = self._build_task_drafts(summary, source_thread_id=source_thread_id)
        return ExternalTaskSyncRequest(
            target=target,
            source_thread_id=source_thread_id,
            requested_by=requested_by,
            task_drafts=task_drafts,
            require_confirmation=True,
            confirmed=confirmed,
        )

    async def sync_prepared_tasks(
        self,
        request: ExternalTaskSyncRequest,
    ) -> ExternalTaskSyncResult:
        if request.require_confirmation and not request.confirmed:
            return ExternalTaskSyncResult(
                status=TaskSyncStatus.REQUIRES_CONFIRMATION,
                target=request.target,
                source_thread_id=request.source_thread_id,
                prepared_drafts=request.task_drafts,
                synced_tasks=[],
                message="external_task_sync_requires_confirmation",
            )

        if self.task_sync_client is None:
            return ExternalTaskSyncResult(
                status=TaskSyncStatus.SYNC_FAILED,
                target=request.target,
                source_thread_id=request.source_thread_id,
                prepared_drafts=request.task_drafts,
                synced_tasks=[],
                message="external_task_sync_not_configured",
            )

        synced_tasks: list[SyncedExternalTask] = []
        try:
            for task_draft in request.task_drafts:
                synced_tasks.append(
                    await self.task_sync_client.create_task(
                        target=request.target,
                        draft=task_draft,
                    )
                )
        except Exception:
            return ExternalTaskSyncResult(
                status=TaskSyncStatus.SYNC_FAILED,
                target=request.target,
                source_thread_id=request.source_thread_id,
                prepared_drafts=request.task_drafts,
                synced_tasks=synced_tasks,
                message="external_task_sync_failed",
            )

        return ExternalTaskSyncResult(
            status=TaskSyncStatus.SYNCED,
            target=request.target,
            source_thread_id=request.source_thread_id,
            prepared_drafts=request.task_drafts,
            synced_tasks=synced_tasks,
            message=f"external_task_sync_succeeded:{len(synced_tasks)}",
        )

    def _build_task_drafts(
        self,
        summary: StructuredSummary,
        *,
        source_thread_id: str,
    ) -> list[ExternalTaskDraft]:
        task_drafts: list[ExternalTaskDraft] = []

        if summary.todo_draft:
            for todo_item in summary.todo_draft:
                task_drafts.append(
                    ExternalTaskDraft(
                        title=todo_item.title,
                        description=self._build_task_description(
                            summary=summary,
                            source_thread_id=source_thread_id,
                            task_title=todo_item.title,
                            rationale=todo_item.rationale,
                        ),
                        owner_hint=todo_item.owner_hint,
                        labels=self._build_labels(summary),
                        citations=summary.citations,
                    )
                )
            return task_drafts

        for action in summary.next_actions[:3]:
            task_drafts.append(
                ExternalTaskDraft(
                    title=action,
                    description=self._build_task_description(
                        summary=summary,
                        source_thread_id=source_thread_id,
                        task_title=action,
                        rationale=None,
                    ),
                    owner_hint=None,
                    labels=self._build_labels(summary),
                    citations=summary.citations,
                )
            )

        if task_drafts:
            return task_drafts

        for missing_item in summary.missing_information[:2]:
            task_drafts.append(
                ExternalTaskDraft(
                    title=f"补充{missing_item}",
                    description=self._build_task_description(
                        summary=summary,
                        source_thread_id=source_thread_id,
                        task_title=f"补充{missing_item}",
                        rationale="当前缺少关键证据，需要人工补充。",
                    ),
                    owner_hint=None,
                    labels=self._build_labels(summary),
                    citations=summary.citations,
                )
            )

        if task_drafts:
            return task_drafts

        task_drafts.append(
            ExternalTaskDraft(
                title="Review incident conclusion",
                description=self._build_task_description(
                    summary=summary,
                    source_thread_id=source_thread_id,
                    task_title="Review incident conclusion",
                    rationale="Summary did not contain explicit follow-up items.",
                ),
                owner_hint=None,
                labels=self._build_labels(summary),
                citations=summary.citations,
            )
        )

        return task_drafts

    def _build_task_description(
        self,
        *,
        summary: StructuredSummary,
        source_thread_id: str,
        task_title: str,
        rationale: str | None,
    ) -> str:
        lines = [
            f"Source thread: {source_thread_id}",
            f"Task draft: {task_title}",
            f"Current assessment: {summary.current_assessment}",
        ]

        if summary.conclusion_summary:
            lines.append(f"Conclusion summary: {summary.conclusion_summary}")

        if rationale:
            lines.append(f"Rationale: {rationale}")

        if summary.missing_information:
            lines.append(
                "Missing information: "
                + ", ".join(summary.missing_information[:3])
            )

        if summary.citations:
            citation_refs = ", ".join(citation.source_uri for citation in summary.citations[:3])
            lines.append(f"Citations: {citation_refs}")

        return "\n".join(lines)

    def _build_labels(self, summary: StructuredSummary) -> list[str]:
        labels = ["incident-draft"]
        if summary.confidence.value:
            labels.append(f"confidence-{summary.confidence.value}")
        return labels
