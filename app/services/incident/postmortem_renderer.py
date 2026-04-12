from app.models.contracts import OrgPostmortemStyle, PostmortemDraft


class PostmortemRenderer:
    DEFAULT_LABELS = {
        "incident_summary": "事件摘要：",
        "impact_summary": "影响范围：",
        "timeline": "时间线：",
        "root_cause_hypothesis": "根因假设：",
        "resolution_summary": "处理与恢复：",
        "follow_up_actions": "后续动作：",
        "open_questions": "待确认问题：",
        "citations": "参考来源：",
    }

    def render(
        self,
        draft: PostmortemDraft,
        *,
        org_style: OrgPostmortemStyle | None = None,
    ) -> str:
        labels = dict(self.DEFAULT_LABELS)
        if org_style is not None:
            labels.update(org_style.section_labels)

        sections = [
            "复盘草稿：",
            draft.title,
            "",
            labels["incident_summary"],
            draft.incident_summary,
            "",
            labels["impact_summary"],
            draft.impact_summary,
            "",
            labels["timeline"],
            *self._render_timeline(draft.timeline),
            "",
            labels["root_cause_hypothesis"],
            draft.root_cause_hypothesis,
            "",
            labels["resolution_summary"],
            draft.resolution_summary,
            "",
            labels["follow_up_actions"],
            *self._render_list(draft.follow_up_actions),
            "",
            labels["open_questions"],
            *self._render_list(draft.open_questions),
            "",
            labels["citations"],
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
