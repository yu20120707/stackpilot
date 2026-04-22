from app.models.contracts import (
    AnalysisResultStatus,
    ConfidenceLevel,
    KnowledgeCitation,
    SourceType,
    StructuredSummary,
    TemporaryFailureReply,
    TodoDraftItem,
    TriggerCommand,
)
from app.services.incident.reply_renderer import ReplyRenderer


def build_citations() -> list[KnowledgeCitation]:
    return [
        KnowledgeCitation(
            source_type=SourceType.KNOWLEDGE_DOC,
            label="Payment Service SOP",
            source_uri="data/knowledge/payment-sop.md",
            snippet="When the payment service shows a 5xx spike after deployment...",
        )
    ]


def test_reply_renderer_formats_success_reply() -> None:
    renderer = ReplyRenderer()
    reply = StructuredSummary(
        status=AnalysisResultStatus.SUCCESS,
        confidence=ConfidenceLevel.MEDIUM,
        current_assessment="当前更像是一次发布后导致的支付服务异常。",
        known_facts=["支付服务出现 5xx 告警", "线程中提到已经执行回滚"],
        impact_scope="当前主要影响支付相关请求。",
        next_actions=["补充错误日志", "确认最近一次发布内容"],
        citations=build_citations(),
        missing_information=["详细错误日志"],
    )

    rendered = renderer.render(reply)

    assert "当前判断：" in rendered
    assert "已知事实：" in rendered
    assert "影响范围：" in rendered
    assert "下一步建议：" in rendered
    assert "参考来源：" in rendered
    assert "Payment Service SOP" in rendered
    assert "payment-sop.md" in rendered
    assert "缺少信息：" not in rendered


def test_reply_renderer_formats_analyze_incident_reply() -> None:
    renderer = ReplyRenderer()
    reply = StructuredSummary(
        status=AnalysisResultStatus.SUCCESS,
        confidence=ConfidenceLevel.MEDIUM,
        current_assessment="当前更像是一次发布后导致的支付服务异常。",
        known_facts=["支付服务出现 5xx 告警"],
        impact_scope="当前主要影响支付相关请求。",
        next_actions=["补充错误日志", "确认最近一次发布内容"],
        citations=build_citations(),
        missing_information=["详细错误日志"],
    )

    rendered = renderer.render_for_trigger(reply, trigger_command=TriggerCommand.ANALYZE_INCIDENT)

    assert "以下是基于当前告警证据的分诊结果：" in rendered
    assert "当前判断：" in rendered
    assert "Payment Service SOP" in rendered


def test_reply_renderer_formats_insufficient_context_reply() -> None:
    renderer = ReplyRenderer()
    reply = StructuredSummary(
        status=AnalysisResultStatus.INSUFFICIENT_CONTEXT,
        confidence=ConfidenceLevel.LOW,
        current_assessment="当前信息不足，暂时无法判断完整原因和影响范围。",
        known_facts=["线程中存在异常讨论"],
        impact_scope="当前无法可靠判断。",
        next_actions=["补充错误日志"],
        citations=[],
        missing_information=["错误日志", "最近变更记录"],
    )

    rendered = renderer.render(reply)

    assert "缺少信息：" in rendered
    assert "- 错误日志" in rendered
    assert "- 最近变更记录" in rendered


def test_reply_renderer_formats_temporary_failure_reply() -> None:
    renderer = ReplyRenderer()
    reply = TemporaryFailureReply(
        status=AnalysisResultStatus.TEMPORARY_FAILURE,
        headline="本次分析未完整完成",
        known_facts=["已读取当前线程"],
        missing_information=["完整分析结果"],
        citations=build_citations(),
        retry_hint="请稍后重试，或补充更多上下文后再次触发。",
    )

    rendered = renderer.render(reply)

    assert "状态：" in rendered
    assert "当前已知：" in rendered
    assert "缺少信息：" in rendered
    assert "建议：" in rendered
    assert "请稍后重试" in rendered
    assert "Payment Service SOP" in rendered


def test_reply_renderer_includes_conclusion_summary_and_todo_draft() -> None:
    renderer = ReplyRenderer()
    reply = StructuredSummary(
        status=AnalysisResultStatus.SUCCESS,
        confidence=ConfidenceLevel.MEDIUM,
        current_assessment="Rollback is reducing the payment error rate.",
        known_facts=["Payment service 5xx alerts dropped after rollback."],
        impact_scope="Payment-related requests were affected during the incident window.",
        next_actions=["Confirm the final error-rate trend."],
        citations=[],
        missing_information=["Detailed error logs"],
        conclusion_summary="The thread has largely converged on a rollback-related incident conclusion.",
        todo_draft=[
            TodoDraftItem(
                title="Confirm the final error-rate trend.",
                owner_hint="待确认",
                rationale="The thread still needs a final stability check.",
            )
        ],
    )

    rendered = renderer.render_for_trigger(reply, trigger_command=TriggerCommand.SUMMARIZE_THREAD)

    assert "结论摘要：" in rendered
    assert "待办草稿：" in rendered
    assert "- [草稿] Confirm the final error-rate trend." in rendered
    assert "负责人待确认：待确认" in rendered
    assert "依据：The thread still needs a final stability check." in rendered
