from __future__ import annotations

from app.models.contracts import CodeReviewDraft, CodeReviewFailureReply, PendingIncidentAction, ReviewReplyPayload


RISK_LABELS = {
    "low": "低",
    "medium": "中",
    "high": "高",
}


class ReviewRenderer:
    def render(self, reply: ReviewReplyPayload) -> str:
        if isinstance(reply, CodeReviewDraft):
            return self._render_review_draft(reply)
        if isinstance(reply, CodeReviewFailureReply):
            return self._render_failure_reply(reply)
        raise ValueError(f"Unsupported review reply payload type: {type(reply)!r}")

    def render_pending_actions(self, actions: list[PendingIncidentAction]) -> str:
        if not actions:
            return ""

        lines = ["待审批动作："]
        for action in actions:
            lines.append(f"- [{action.action_id}] {action.title}")
            lines.append(f"  {action.preview}")
            lines.append(f"  批准命令：批准动作 {action.action_id}")
        return "\n".join(lines)

    def render_publish_comment(self, review_draft: CodeReviewDraft) -> str:
        lines = [
            "## AI Code Review Draft",
            "",
            f"- Overall assessment: {review_draft.overall_assessment}",
            f"- Overall risk: {review_draft.overall_risk.value}",
            "",
            "### Findings",
        ]
        if not review_draft.findings:
            lines.append("- No high-confidence findings in this draft.")
        else:
            for finding in review_draft.findings:
                location = (
                    f" ({finding.file_path}:{finding.line_start})"
                    if finding.file_path and finding.line_start
                    else f" ({finding.file_path})"
                    if finding.file_path
                    else ""
                )
                lines.append(f"- [{finding.severity.value}] {finding.title}{location}")
                lines.append(f"  {finding.summary}")
        if review_draft.missing_context:
            lines.extend(["", "### Missing context"])
            for item in review_draft.missing_context:
                lines.append(f"- {item}")
        return "\n".join(lines).strip()

    def _render_review_draft(self, review_draft: CodeReviewDraft) -> str:
        risk_label = RISK_LABELS.get(review_draft.overall_risk.value, review_draft.overall_risk.value)
        lines = [
            "代码审查结论：",
            review_draft.overall_assessment,
            "",
            "整体风险：",
            risk_label,
            "",
            "Findings：",
        ]
        if not review_draft.findings:
            lines.append("- 暂未发现高置信问题")
        else:
            for finding in review_draft.findings:
                location = self._render_location(finding.file_path, finding.line_start, finding.line_end)
                lines.append(f"- [{RISK_LABELS.get(finding.severity.value, finding.severity.value)}] {finding.title}{location}")
                lines.append(f"  {finding.summary}")
                for evidence in finding.evidence[:2]:
                    lines.append(f"  证据：{evidence.label} ({evidence.source_uri})")
                    lines.append(f"  {evidence.snippet}")

        if review_draft.missing_context:
            lines.extend(["", "缺少上下文："])
            lines.extend(f"- {item}" for item in review_draft.missing_context)

        lines.extend(
            [
                "",
                "发布建议：",
                review_draft.publish_recommendation,
            ]
        )
        return "\n".join(lines).strip()

    def _render_failure_reply(self, reply: CodeReviewFailureReply) -> str:
        lines = [
            "状态：",
            reply.headline,
            "",
            "当前限制：",
            *(f"- {item}" for item in (reply.known_limits or ["暂无"])),
            "",
            "缺少信息：",
            *(f"- {item}" for item in (reply.missing_context or ["暂无"])),
            "",
            "建议：",
            reply.retry_hint,
        ]
        return "\n".join(lines).strip()

    def _render_location(
        self,
        file_path: str | None,
        line_start: int | None,
        line_end: int | None,
    ) -> str:
        if not file_path:
            return ""
        if line_start is None:
            return f" ({file_path})"
        if line_end is not None and line_end != line_start:
            return f" ({file_path}:{line_start}-{line_end})"
        return f" ({file_path}:{line_start})"
