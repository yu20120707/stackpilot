from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.models.contracts import (
    ExternalTaskDraft,
    ExternalTaskTarget,
    SyncedExternalTask,
)


@dataclass(slots=True)
class TaskSyncClientConfig:
    base_url: str
    api_key: str
    project_key: str | None = None
    timeout_seconds: int = 30


class TaskSyncClient:
    def __init__(
        self,
        config: TaskSyncClientConfig | None = None,
        *,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.config = config
        self.http_client = http_client

    async def create_task(
        self,
        *,
        target: ExternalTaskTarget,
        draft: ExternalTaskDraft,
    ) -> SyncedExternalTask:
        if self.config is None or self.http_client is None:
            raise NotImplementedError("Task sync requires an HTTP client and config.")

        request_body = {
            "target": target.value,
            "project_key": self.config.project_key,
            "title": draft.title,
            "description": draft.description,
            "owner_hint": draft.owner_hint,
            "labels": draft.labels,
            "citations": [citation.model_dump(mode="json") for citation in draft.citations],
        }
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }

        response = await self.http_client.post(
            f"{self.config.base_url.rstrip('/')}/tasks",
            headers=headers,
            json=request_body,
            timeout=self.config.timeout_seconds,
        )
        response.raise_for_status()

        payload = response.json()
        task_id = payload["data"]["task_id"]
        task_url = payload["data"].get("task_url")

        if not isinstance(task_id, str) or not task_id.strip():
            raise ValueError("Task sync response does not contain a usable task_id.")

        normalized_task_url = task_url.strip() if isinstance(task_url, str) and task_url.strip() else None
        return SyncedExternalTask(
            title=draft.title,
            external_id=task_id.strip(),
            external_url=normalized_task_url,
        )

    async def aclose(self) -> None:
        if self.http_client is not None:
            await self.http_client.aclose()
