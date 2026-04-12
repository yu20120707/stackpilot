from app.models.contracts import (
    AnalysisResultStatus,
    ReplyPayload,
    StructuredSummary,
    TemporaryFailureReply,
    TriggerCommand,
)


class ReplyRenderer:
    def render(self, reply: ReplyPayload) -> str:
        return self.render_for_trigger(reply)

    def render_for_trigger(
        self,
        reply: ReplyPayload,
        trigger_command: TriggerCommand | None = None,
    ) -> str:
        if isinstance(reply, StructuredSummary):
            return self._render_structured_summary(reply, trigger_command=trigger_command)

        if isinstance(reply, TemporaryFailureReply):
            return self._render_temporary_failure(reply, trigger_command=trigger_command)

        raise ValueError(f"Unsupported reply payload type: {type(reply)!r}")

    def _render_structured_summary(
        self,
        reply: StructuredSummary,
        *,
        trigger_command: TriggerCommand | None = None,
    ) -> str:
        prefix = self._build_follow_up_prefix(trigger_command)
        sections = [
            *(prefix if prefix else []),
            "当前判断：",
            reply.current_assessment,
            "",
            "已知事实：",
            *self._render_list(reply.known_facts),
            "",
            "影响范围：",
            reply.impact_scope,
            "",
            "下一步建议：",
            *self._render_list(reply.next_actions),
            "",
            "参考来源：",
            *self._render_citations(reply.citations),
        ]

        if reply.conclusion_summary:
            sections.extend(
                [
                    "",
                    "结论摘要：",
                    reply.conclusion_summary,
                ]
            )

        if reply.todo_draft:
            sections.extend(
                [
                    "",
                    "待办草稿：",
                    *self._render_todo_draft(reply.todo_draft),
                ]
            )

        if reply.status == AnalysisResultStatus.INSUFFICIENT_CONTEXT and reply.missing_information:
            sections.extend(
                [
                    "",
                    "缺少信息：",
                    *self._render_list(reply.missing_information),
                ]
            )

        return "\n".join(sections).strip()

    def _render_temporary_failure(
        self,
        reply: TemporaryFailureReply,
        *,
        trigger_command: TriggerCommand | None = None,
    ) -> str:
        prefix = self._build_follow_up_prefix(trigger_command)
        sections = [
            *(prefix if prefix else []),
            "状态：",
            reply.headline,
            "",
            "当前已知：",
            *self._render_list(reply.known_facts),
            "",
            "缺少信息：",
            *self._render_list(reply.missing_information),
            "",
            "参考来源：",
            *self._render_citations(reply.citations),
            "",
            "建议：",
            reply.retry_hint,
        ]

        return "\n".join(sections).strip()

    def _build_follow_up_prefix(
        self,
        trigger_command: TriggerCommand | None,
    ) -> list[str]:
        if trigger_command is TriggerCommand.SUMMARIZE_THREAD:
            return ["以下是基于当前线程的更新总结：", ""]

        if trigger_command is TriggerCommand.RERUN_ANALYSIS:
            return ["以下是基于最新信息的更新分析：", ""]

        return []

    def _render_list(self, items: list[str]) -> list[str]:
        if not items:
            return ["- 暂无"]

        return [f"- {item}" for item in items]

    def _render_citations(self, citations: list) -> list[str]:
        if not citations:
            return ["- 暂无"]

        rendered: list[str] = []
        for citation in citations:
            rendered.append(f"- {citation.label} ({citation.source_uri})")
            rendered.append(f"  {citation.snippet}")
        return rendered

    def _render_todo_draft(self, todo_draft: list) -> list[str]:
        rendered: list[str] = []
        for item in todo_draft:
            rendered.append(f"- [草稿] {item.title}")
            details: list[str] = []
            if item.owner_hint:
                details.append(f"负责人待确认：{item.owner_hint}")
            if item.rationale:
                details.append(f"依据：{item.rationale}")
            if details:
                rendered.append(f"  {' | '.join(details)}")

        return rendered or ["- 暂无"]
