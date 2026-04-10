from app.models.contracts import PostmortemDraft


class PostmortemRenderer:
    def render(self, draft: PostmortemDraft) -> str:
        sections = [
            "复盘草稿：",
            draft.title,
            "",
            "事件摘要：",
            draft.incident_summary,
            "",
            "影响范围：",
            draft.impact_summary,
            "",
            "时间线：",
            *self._render_timeline(draft.timeline),
            "",
            "根因假设：",
            draft.root_cause_hypothesis,
            "",
            "处理与恢复：",
            draft.resolution_summary,
            "",
            "后续动作：",
            *self._render_list(draft.follow_up_actions),
            "",
            "待确认问题：",
            *self._render_list(draft.open_questions),
            "",
            "参考来源：",
            *self._render_citations(draft.citations),
        ]

        return "\n".join(sections).strip()

    def _render_timeline(self, timeline: list) -> list[str]:
        if not timeline:
            return ["- 暂无"]
        return [f"- {item.timestamp_hint} {item.event}" for item in timeline]

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
