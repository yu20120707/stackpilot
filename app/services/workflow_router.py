from __future__ import annotations

from app.models.contracts import NormalizedFeishuMessageEvent, TriggerCommand
from app.services.feishu_live_flow import FeishuLiveFlow
from app.services.review.flow import CodeReviewFlow


class WorkflowRouter:
    def __init__(
        self,
        *,
        incident_flow: FeishuLiveFlow,
        code_review_flow: CodeReviewFlow,
    ) -> None:
        self.incident_flow = incident_flow
        self.code_review_flow = code_review_flow

    async def process_trigger(
        self,
        *,
        trigger_command: TriggerCommand,
        trigger_event: NormalizedFeishuMessageEvent,
    ) -> None:
        if trigger_command is TriggerCommand.REVIEW_CODE:
            await self.code_review_flow.process_trigger(
                trigger_command=trigger_command,
                trigger_event=trigger_event,
            )
            return

        if trigger_command is TriggerCommand.APPROVE_ACTION:
            handled = await self.code_review_flow.process_approval(
                trigger_event=trigger_event,
            )
            if handled:
                return

        await self.incident_flow.process_trigger(
            trigger_command=trigger_command,
            trigger_event=trigger_event,
        )
