from app.clients.feishu_client import FeishuClient
from app.models.contracts import (
    AnalysisRequest,
    FeishuThreadMessageRecord,
    FollowUpContext,
    NormalizedFeishuMessageEvent,
    ThreadMessage,
    TriggerCommand,
)
from app.services.command_parser import is_follow_up_trigger


class ThreadReader:
    def __init__(self, feishu_client: FeishuClient, max_thread_messages: int = 50) -> None:
        self.feishu_client = feishu_client
        self.max_thread_messages = max_thread_messages

    async def load_thread(
        self,
        *,
        chat_id: str,
        message_id: str,
        thread_id: str,
        trigger_event: NormalizedFeishuMessageEvent,
    ) -> list[ThreadMessage]:
        thread_response = await self.feishu_client.fetch_thread_messages(
            chat_id=chat_id,
            message_id=message_id,
            thread_id=thread_id,
        )
        return self._normalize_thread_messages(
            raw_messages=thread_response.thread_messages,
            trigger_event=trigger_event,
        )

    async def build_analysis_request(
        self,
        *,
        trigger_command: TriggerCommand,
        trigger_event: NormalizedFeishuMessageEvent,
    ) -> AnalysisRequest:
        thread_messages = await self.load_thread(
            chat_id=trigger_event.chat_id,
            message_id=trigger_event.message_id,
            thread_id=trigger_event.thread_id,
            trigger_event=trigger_event,
        )
        return AnalysisRequest(
            trigger_command=trigger_command,
            chat_id=trigger_event.chat_id,
            thread_id=trigger_event.thread_id,
            trigger_message_id=trigger_event.message_id,
            user_id=trigger_event.sender_id,
            user_display_name=trigger_event.sender_name,
            thread_messages=thread_messages,
            follow_up_context=self._build_follow_up_context(
                trigger_command=trigger_command,
                thread_messages=thread_messages,
            ),
        )

    def _normalize_thread_messages(
        self,
        *,
        raw_messages: list[FeishuThreadMessageRecord],
        trigger_event: NormalizedFeishuMessageEvent,
    ) -> list[ThreadMessage]:
        bounded_messages = raw_messages[-self.max_thread_messages :]
        normalized_messages: list[ThreadMessage] = []

        for raw_message in bounded_messages:
            text = (raw_message.text or "").strip()
            if not text:
                continue

            sender_name = (raw_message.sender_name or "").strip() or "Unknown"
            sent_at = raw_message.sent_at or trigger_event.event_time
            normalized_messages.append(
                ThreadMessage(
                    message_id=raw_message.message_id,
                    sender_name=sender_name,
                    sent_at=sent_at,
                    text=text,
                )
            )

        if normalized_messages:
            return normalized_messages

        return [
            ThreadMessage(
                message_id=trigger_event.message_id,
                sender_name=trigger_event.sender_name or "Unknown",
                sent_at=trigger_event.event_time,
                text=trigger_event.message_text,
            )
        ]

    def _build_follow_up_context(
        self,
        *,
        trigger_command: TriggerCommand,
        thread_messages: list[ThreadMessage],
    ) -> FollowUpContext | None:
        if not is_follow_up_trigger(trigger_command):
            return None

        previous_summary_index = self._find_previous_summary_index(thread_messages)
        if previous_summary_index is None:
            return FollowUpContext(
                previous_summary=None,
                new_messages=thread_messages[-3:],
            )

        previous_summary = thread_messages[previous_summary_index].text
        new_messages = thread_messages[previous_summary_index + 1 :]
        return FollowUpContext(
            previous_summary=previous_summary,
            new_messages=new_messages,
        )

    def _find_previous_summary_index(self, thread_messages: list[ThreadMessage]) -> int | None:
        for index in range(len(thread_messages) - 1, -1, -1):
            if self._looks_like_previous_analysis(thread_messages[index].text):
                return index
        return None

    def _looks_like_previous_analysis(self, text: str) -> bool:
        summary_markers = (
            "当前判断：",
            "已知事实：",
            "影响范围：",
            "下一步建议：",
            "参考来源：",
            "结论摘要：",
            "待办草稿：",
            "状态：",
            "缺少信息：",
        )
        return any(marker in text for marker in summary_markers)
