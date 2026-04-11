from app.models.contracts import (
    KnowledgeCitation,
    OrgPostmortemStyle,
    PostmortemDraft,
    PostmortemStatus,
    PostmortemTimelineEntry,
    SourceType,
)
from app.services.postmortem_renderer import PostmortemRenderer


def test_postmortem_renderer_formats_reviewable_postmortem_draft() -> None:
    renderer = PostmortemRenderer()
    draft = PostmortemDraft(
        status=PostmortemStatus.DRAFT,
        title="Payment release regression after retry middleware change",
        incident_summary="The discussion converged on a release-related payment incident that improved after rollback.",
        impact_summary="Payment-related requests were affected during the incident window.",
        timeline=[
            PostmortemTimelineEntry(
                timestamp_hint="2026-04-10T01:00:00+08:00",
                event="Alerting reported a payment service 5xx spike after release.",
            )
        ],
        root_cause_hypothesis="The strongest current hypothesis is a retry middleware regression introduced by the release.",
        resolution_summary="Rollback stabilized the service, pending log-backed confirmation.",
        follow_up_actions=["Confirm the final post-rollback error-rate trend."],
        open_questions=["What was the exact user-impact window?"],
        citations=[
            KnowledgeCitation(
                source_type=SourceType.KNOWLEDGE_DOC,
                label="Payment Release 2026-04-10",
                source_uri="https://kb.example.local/releases/payment-2026-04-10",
                snippet="The payment-api release touched retry middleware and idempotency handling.",
            )
        ],
    )

    rendered = renderer.render(draft)

    assert "复盘草稿：" in rendered
    assert "事件摘要：" in rendered
    assert "影响范围：" in rendered
    assert "时间线：" in rendered
    assert "根因假设：" in rendered
    assert "处理与恢复：" in rendered
    assert "后续动作：" in rendered
    assert "待确认问题：" in rendered
    assert "参考来源：" in rendered
    assert "Payment Release 2026-04-10" in rendered


def test_postmortem_renderer_respects_org_style_section_labels() -> None:
    renderer = PostmortemRenderer()
    draft = PostmortemDraft(
        status=PostmortemStatus.DRAFT,
        title="[SEV-2] Payment release regression",
        incident_summary="The discussion converged on a release-related payment incident that improved after rollback.",
        impact_summary="Payment-related requests were affected during the incident window.",
        timeline=[],
        root_cause_hypothesis="Retry middleware regression.",
        resolution_summary="Rollback stabilized the service.",
        follow_up_actions=["团队跟进：Confirm final metrics."],
        open_questions=["Exact user-impact window."],
        citations=[],
    )

    rendered = renderer.render(
        draft,
        org_style=OrgPostmortemStyle(
            template_name="enterprise-standard",
            section_labels={
                "incident_summary": "背景摘要：",
                "follow_up_actions": "团队后续动作：",
            },
        ),
    )

    assert "背景摘要：" in rendered
    assert "团队后续动作：" in rendered
