from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from app.clients.llm_client import (
    LLMClient,
    LLMClientError,
    LLMInvalidResponseError,
)
from app.models.contracts import (
    AnalysisRequest,
    AnalysisResultStatus,
    ConfidenceLevel,
    KnowledgeCitation,
    ReplyPayload,
    SourceType,
    StructuredSummary,
    TemporaryFailureReply,
    TodoDraftItem,
    TriggerCommand,
)

class AnalysisService:
    def __init__(
        self,
        llm_client: LLMClient,
        *,
        prompt_path: Path | None = None,
    ) -> None:
        self.llm_client = llm_client
        self.prompt_path = prompt_path or Path(__file__).resolve().parents[2] / "prompts" / "analysis_prompt.md"

    async def summarize(
        self,
        request: AnalysisRequest,
        *,
        citations: list[KnowledgeCitation] | None = None,
    ) -> ReplyPayload:
        citations = citations or []

        if self._should_return_insufficient_context(request, citations):
            if request.trigger_command is TriggerCommand.ANALYZE_INCIDENT:
                return self._finalize_reply(
                    self._build_incident_insufficient_context_reply(request, citations),
                    request=request,
                    citations=citations,
                )
            return self._finalize_reply(
                self._build_insufficient_context_reply(request, citations),
                request=request,
                citations=citations,
            )

        system_prompt = self._load_system_prompt()
        user_prompt = self._build_user_prompt(request, citations)

        try:
            raw_response = await self.llm_client.generate_structured_summary(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
            summary = self._parse_summary_response(raw_response)
        except (LLMClientError, LLMInvalidResponseError, ValidationError, ValueError, json.JSONDecodeError):
            return self._build_temporary_failure_reply(request, citations)

        return self._finalize_reply(
            summary,
            request=request,
            citations=citations,
        )

    def _load_system_prompt(self) -> str:
        return self.prompt_path.read_text(encoding="utf-8").strip()

    def _build_user_prompt(
        self,
        request: AnalysisRequest,
        citations: list[KnowledgeCitation],
    ) -> str:
        thread_context = "\n".join(
            f"- [{message.sent_at.isoformat()}] {message.sender_name}: {message.text}"
            for message in request.thread_messages
        )
        references = "\n".join(
            f"- {citation.label} | {citation.source_uri} | {citation.snippet}"
            for citation in citations
        )
        references = references or "- none"

        follow_up_context = self._build_follow_up_prompt_block(request)
        mode_requirements = self._build_mode_specific_prompt_block(request)

        return (
            f"analysis_mode: {request.trigger_command.value}\n"
            f"thread_context:\n{thread_context}\n\n"
            f"references:\n{references}\n"
            f"{follow_up_context}"
            f"{mode_requirements}"
        )

    def _parse_summary_response(self, raw_response: str) -> StructuredSummary:
        cleaned_response = raw_response.strip()
        if cleaned_response.startswith("```"):
            cleaned_response = cleaned_response.strip("`")
            cleaned_response = cleaned_response.removeprefix("json").strip()

        payload = self._normalize_summary_payload(json.loads(cleaned_response))
        summary = StructuredSummary.model_validate(payload)

        if summary.status not in {
            AnalysisResultStatus.SUCCESS,
            AnalysisResultStatus.INSUFFICIENT_CONTEXT,
        }:
            raise ValueError("LLM returned unsupported status for structured summary")

        return summary

    def _normalize_summary_payload(self, payload: object) -> dict:
        if not isinstance(payload, dict):
            raise ValueError("LLM summary payload must be a JSON object")

        normalized_payload = dict(payload)
        status = normalized_payload.get("status")
        if isinstance(status, str):
            normalized_payload["status"] = self._normalize_status(status)

        impact_scope = normalized_payload.get("impact_scope")
        if isinstance(impact_scope, list):
            normalized_payload["impact_scope"] = " ".join(
                item.strip()
                for item in impact_scope
                if isinstance(item, str) and item.strip()
            )

        citations = normalized_payload.get("citations")
        if isinstance(citations, list):
            normalized_payload["citations"] = [
                normalized_citation
                for item in citations
                if (normalized_citation := self._normalize_citation(item)) is not None
            ]

        return normalized_payload

    def _normalize_status(self, status: str) -> str:
        normalized = status.strip()
        status_map = {
            "mitigation_in_progress": AnalysisResultStatus.SUCCESS.value,
            "monitoring": AnalysisResultStatus.SUCCESS.value,
            "investigating": AnalysisResultStatus.SUCCESS.value,
            "analysis_complete": AnalysisResultStatus.SUCCESS.value,
            "needs_more_info": AnalysisResultStatus.INSUFFICIENT_CONTEXT.value,
            "need_more_info": AnalysisResultStatus.INSUFFICIENT_CONTEXT.value,
        }
        return status_map.get(normalized, normalized)

    def _normalize_citation(self, item: object) -> dict | None:
        if isinstance(item, dict):
            source_type = item.get("source_type")
            normalized_source_type = self._normalize_source_type(source_type)
            if normalized_source_type is None:
                return None

            source_uri = item.get("source_uri")
            label = item.get("label")
            snippet = item.get("snippet")
            if not isinstance(source_uri, str) or not source_uri.strip():
                return None

            normalized_source_uri = source_uri.strip()
            normalized_label = (
                label.strip()
                if isinstance(label, str) and label.strip()
                else normalized_source_uri.rsplit("/", maxsplit=1)[-1]
            )
            normalized_snippet = (
                snippet.strip()
                if isinstance(snippet, str) and snippet.strip()
                else normalized_source_uri
            )

            return {
                "source_type": normalized_source_type,
                "label": normalized_label,
                "source_uri": normalized_source_uri,
                "snippet": normalized_snippet,
            }

        if not isinstance(item, str):
            return None

        normalized = item.strip()
        if not normalized:
            return None

        if normalized.startswith("thread:"):
            return {
                "source_type": SourceType.THREAD_MESSAGE.value,
                "label": "Thread Evidence",
                "source_uri": normalized,
                "snippet": normalized,
            }

        label = normalized.rsplit("/", maxsplit=1)[-1] if "/" in normalized else normalized
        return {
            "source_type": SourceType.KNOWLEDGE_DOC.value,
            "label": label,
            "source_uri": normalized,
            "snippet": normalized,
        }

    def _normalize_source_type(self, source_type: object) -> str | None:
        if not isinstance(source_type, str):
            return None

        normalized = source_type.strip().lower()
        source_type_map = {
            SourceType.THREAD_MESSAGE.value: SourceType.THREAD_MESSAGE.value,
            "thread": SourceType.THREAD_MESSAGE.value,
            SourceType.KNOWLEDGE_DOC.value: SourceType.KNOWLEDGE_DOC.value,
            "doc": SourceType.KNOWLEDGE_DOC.value,
            "knowledge": SourceType.KNOWLEDGE_DOC.value,
        }
        return source_type_map.get(normalized)

    def _should_return_insufficient_context(
        self,
        request: AnalysisRequest,
        citations: list[KnowledgeCitation],
    ) -> bool:
        combined_text = " ".join(message.text.strip() for message in request.thread_messages if message.text.strip())
        if request.follow_up_context and request.follow_up_context.previous_summary:
            return False

        if citations:
            return False

        if len(request.thread_messages) <= 1:
            return True

        return len(combined_text) < 120

    def _build_follow_up_prompt_block(self, request: AnalysisRequest) -> str:
        if request.follow_up_context is None:
            return ""

        previous_summary = request.follow_up_context.previous_summary or "none"
        new_messages = "\n".join(
            f"- [{message.sent_at.isoformat()}] {message.sender_name}: {message.text}"
            for message in request.follow_up_context.new_messages
        ) or "- none"

        return (
            "\nfollow_up_context:\n"
            f"previous_summary:\n{previous_summary}\n\n"
            f"new_messages_since_previous_summary:\n{new_messages}\n"
        )

    def _build_mode_specific_prompt_block(self, request: AnalysisRequest) -> str:
        if request.trigger_command is TriggerCommand.ANALYZE_INCIDENT:
            return (
                "\nincident_triage_requirements:\n"
                "- treat this mode as first-pass incident triage, not root cause analysis\n"
                "- prioritize severity, affected surface, missing evidence, and the first safe action\n"
                "- separate observed facts from hypotheses\n"
                "- if the evidence is weak, prefer insufficient_context with low confidence\n"
                "- next_actions should start with logs, metrics, traces, recent change records, and owner routing\n"
            )

        if request.trigger_command is not TriggerCommand.SUMMARIZE_THREAD:
            return ""

        return (
            "\nclosing_summary_requirements:\n"
            "- include conclusion_summary: one concise closing summary for the current thread\n"
            "- include todo_draft: array of objects with title, owner_hint, rationale\n"
            "- todo_draft items are draft suggestions only and are not synced externally\n"
        )

    def _finalize_reply(
        self,
        reply: ReplyPayload,
        *,
        request: AnalysisRequest,
        citations: list[KnowledgeCitation],
    ) -> ReplyPayload:
        if isinstance(reply, StructuredSummary):
            return self._finalize_structured_summary(
                reply,
                request=request,
                citations=citations,
            )
        return reply

    def _finalize_structured_summary(
        self,
        summary: StructuredSummary,
        *,
        request: AnalysisRequest,
        citations: list[KnowledgeCitation],
    ) -> StructuredSummary:
        update: dict[str, object] = {"citations": citations}

        if request.trigger_command is TriggerCommand.SUMMARIZE_THREAD:
            update["conclusion_summary"] = (
                summary.conclusion_summary or self._build_conclusion_summary(summary)
            )
            update["todo_draft"] = summary.todo_draft or self._build_todo_draft(summary)

        return summary.model_copy(update=update)

    def _build_conclusion_summary(self, summary: StructuredSummary) -> str:
        if summary.status is AnalysisResultStatus.INSUFFICIENT_CONTEXT:
            if summary.missing_information:
                missing = "\u3001".join(summary.missing_information[:2])
                return f"{summary.current_assessment} \u5f53\u524d\u4ecd\u7f3a\u5c11\uff1a{missing}\u3002"
            return summary.current_assessment

        if summary.impact_scope:
            return (
                f"{summary.current_assessment} "
                f"\u5f53\u524d\u7ebf\u7a0b\u5df2\u5f62\u6210\u76f8\u5bf9\u7a33\u5b9a\u7684\u7ed3\u8bba\uff0c"
                f"\u5f71\u54cd\u8303\u56f4\u53ef\u5148\u6309\u201c{summary.impact_scope}\u201d\u7406\u89e3\u3002"
            )

        return summary.current_assessment

    def _build_todo_draft(self, summary: StructuredSummary) -> list[TodoDraftItem]:
        todo_items: list[TodoDraftItem] = []

        for index, action in enumerate(summary.next_actions[:3]):
            rationale = (
                summary.missing_information[index]
                if index < len(summary.missing_information)
                else "\u6765\u81ea\u5f53\u524d\u7ebf\u7a0b\u7684\u4e0b\u4e00\u6b65\u5efa\u8bae\u3002"
            )
            todo_items.append(
                TodoDraftItem(
                    title=action,
                    owner_hint="\u5f85\u786e\u8ba4",
                    rationale=rationale,
                )
            )

        if todo_items:
            return todo_items

        for missing_item in summary.missing_information[:2]:
            title = (
                missing_item
                if missing_item.startswith("\u8865\u5145")
                else f"\u8865\u5145{missing_item}"
            )
            todo_items.append(
                TodoDraftItem(
                    title=title,
                    owner_hint="\u5f85\u786e\u8ba4",
                    rationale=(
                        "\u5f53\u524d\u7ebf\u7a0b\u7f3a\u5c11\u5173\u952e\u4fe1\u606f\uff0c"
                        "\u9700\u8981\u4eba\u5de5\u8ddf\u8fdb\u3002"
                    ),
                )
            )

        return todo_items

    def _build_insufficient_context_reply(
        self,
        request: AnalysisRequest,
        citations: list[KnowledgeCitation],
    ) -> StructuredSummary:
        return StructuredSummary(
            status=AnalysisResultStatus.INSUFFICIENT_CONTEXT,
            confidence=ConfidenceLevel.LOW,
            current_assessment="当前信息不足，暂时无法判断完整原因和影响范围。",
            known_facts=self._extract_known_facts(request),
            impact_scope="当前无法可靠判断。",
            next_actions=self._build_next_actions(),
            citations=citations,
            missing_information=self._build_missing_information(request),
        )

    def _build_incident_insufficient_context_reply(
        self,
        request: AnalysisRequest,
        citations: list[KnowledgeCitation],
    ) -> StructuredSummary:
        return StructuredSummary(
            status=AnalysisResultStatus.INSUFFICIENT_CONTEXT,
            confidence=ConfidenceLevel.LOW,
            current_assessment="当前告警证据不足，先补齐日志、指标、trace 和最近变更，再判断影响范围和可能原因。",
            known_facts=self._extract_known_facts(request),
            impact_scope="当前无法可靠判断。",
            next_actions=self._build_incident_next_actions(),
            citations=citations,
            missing_information=self._build_incident_missing_information(request),
        )

    def _build_temporary_failure_reply(
        self,
        request: AnalysisRequest,
        citations: list[KnowledgeCitation],
    ) -> TemporaryFailureReply:
        return TemporaryFailureReply(
            status=AnalysisResultStatus.TEMPORARY_FAILURE,
            headline="本次分析未完整完成",
            known_facts=self._extract_known_facts(request),
            missing_information=["完整分析结果"],
            citations=citations,
            retry_hint="请稍后重试，或补充更多上下文后再次触发。",
        )

    def _extract_known_facts(self, request: AnalysisRequest) -> list[str]:
        facts: list[str] = []
        for message in request.thread_messages[:3]:
            text = message.text.strip()
            if text and text not in facts:
                facts.append(text)
        return facts

    def _build_next_actions(self) -> list[str]:
        return [
            "补充错误日志",
            "确认最近变更或发布记录",
            "补充影响范围和当前恢复进展",
        ]

    def _build_incident_next_actions(self) -> list[str]:
        return [
            "补充错误日志、异常栈和 trace_id",
            "确认受影响服务、环境和错误率曲线",
            "对照最近发布、配置或开关变更",
            "确认当前处置动作和负责人",
        ]

    def _build_missing_information(self, request: AnalysisRequest) -> list[str]:
        observed_text = " ".join(message.text.lower() for message in request.thread_messages)
        missing: list[str] = []

        if "log" not in observed_text and "日志" not in observed_text:
            missing.append("错误日志")
        if "deploy" not in observed_text and "发布" not in observed_text and "变更" not in observed_text:
            missing.append("最近变更记录")
        if "impact" not in observed_text and "影响" not in observed_text and "用户" not in observed_text:
            missing.append("影响范围")

        return missing or ["更多可验证的上下文"]

    def _build_incident_missing_information(self, request: AnalysisRequest) -> list[str]:
        observed_text = " ".join(message.text.lower() for message in request.thread_messages)
        missing: list[str] = []

        if not any(term in observed_text for term in ("log", "日志", "异常栈", "error")):
            missing.append("错误日志或异常栈")
        if not any(term in observed_text for term in ("trace", "trace_id", "request_id", "链路")):
            missing.append("trace_id / request_id")
        if not any(term in observed_text for term in ("metric", "metrics", "指标", "5xx", "timeout", "rt", "p95", "p99")):
            missing.append("监控指标")
        if not any(term in observed_text for term in ("deploy", "release", "发布", "变更", "配置", "开关")):
            missing.append("最近变更记录")
        if not any(term in observed_text for term in ("impact", "影响", "服务", "接口", "用户", "租户")):
            missing.append("影响范围")

        return missing or ["更多可验证的告警证据"]
