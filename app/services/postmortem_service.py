from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from app.clients.llm_client import LLMClient, LLMClientError, LLMInvalidResponseError
from app.models.contracts import (
    AnalysisRequest,
    PostmortemDraft,
    PostmortemStatus,
    PostmortemTimelineEntry,
    StructuredSummary,
)


class PostmortemService:
    def __init__(
        self,
        llm_client: LLMClient,
        *,
        prompt_path: Path | None = None,
    ) -> None:
        self.llm_client = llm_client
        self.prompt_path = prompt_path or Path(__file__).resolve().parents[1] / "prompts" / "postmortem_prompt.md"

    async def generate_draft(
        self,
        *,
        request: AnalysisRequest,
        summary: StructuredSummary,
    ) -> PostmortemDraft:
        system_prompt = self._load_system_prompt()
        user_prompt = self._build_user_prompt(request=request, summary=summary)

        try:
            raw_response = await self.llm_client.generate_structured_summary(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
            draft = self._parse_draft_response(raw_response)
        except (LLMClientError, LLMInvalidResponseError, ValidationError, ValueError, json.JSONDecodeError):
            draft = self._build_fallback_draft(request=request, summary=summary)

        return draft.model_copy(update={"citations": summary.citations})

    def _load_system_prompt(self) -> str:
        return self.prompt_path.read_text(encoding="utf-8").strip()

    def _build_user_prompt(
        self,
        *,
        request: AnalysisRequest,
        summary: StructuredSummary,
    ) -> str:
        thread_context = "\n".join(
            f"- [{message.sent_at.isoformat()}] {message.sender_name}: {message.text}"
            for message in request.thread_messages
        )
        citations = "\n".join(
            f"- {citation.label} | {citation.source_uri} | {citation.snippet}"
            for citation in summary.citations
        ) or "- none"
        todo_draft = "\n".join(
            f"- {item.title} | owner_hint={item.owner_hint or 'none'} | rationale={item.rationale or 'none'}"
            for item in summary.todo_draft
        ) or "- none"

        return (
            f"thread_id: {request.thread_id}\n"
            f"thread_context:\n{thread_context}\n\n"
            f"structured_summary:\n"
            f"- current_assessment: {summary.current_assessment}\n"
            f"- impact_scope: {summary.impact_scope}\n"
            f"- conclusion_summary: {summary.conclusion_summary or 'none'}\n"
            f"- known_facts: {json.dumps(summary.known_facts, ensure_ascii=False)}\n"
            f"- next_actions: {json.dumps(summary.next_actions, ensure_ascii=False)}\n"
            f"- missing_information: {json.dumps(summary.missing_information, ensure_ascii=False)}\n\n"
            f"todo_draft:\n{todo_draft}\n\n"
            f"references:\n{citations}\n"
        )

    def _parse_draft_response(self, raw_response: str) -> PostmortemDraft:
        cleaned_response = raw_response.strip()
        if cleaned_response.startswith("```"):
            cleaned_response = cleaned_response.strip("`")
            cleaned_response = cleaned_response.removeprefix("json").strip()

        payload = json.loads(cleaned_response)
        draft = PostmortemDraft.model_validate(payload)
        if draft.status is not PostmortemStatus.DRAFT:
            raise ValueError("Postmortem draft must have draft status")
        return draft

    def _build_fallback_draft(
        self,
        *,
        request: AnalysisRequest,
        summary: StructuredSummary,
    ) -> PostmortemDraft:
        title = self._build_title(summary)
        timeline = [
            PostmortemTimelineEntry(
                timestamp_hint=message.sent_at.isoformat(),
                event=message.text,
            )
            for message in request.thread_messages[:5]
        ]
        resolution_summary = summary.conclusion_summary or summary.current_assessment
        follow_up_actions = [item.title for item in summary.todo_draft] or summary.next_actions

        return PostmortemDraft(
            status=PostmortemStatus.DRAFT,
            title=title,
            incident_summary=summary.current_assessment,
            impact_summary=summary.impact_scope,
            timeline=timeline,
            root_cause_hypothesis=summary.current_assessment,
            resolution_summary=resolution_summary,
            follow_up_actions=follow_up_actions,
            open_questions=summary.missing_information,
            citations=summary.citations,
        )

    def _build_title(self, summary: StructuredSummary) -> str:
        base_title = summary.conclusion_summary or summary.current_assessment
        normalized = " ".join(base_title.split())
        if len(normalized) <= 80:
            return normalized
        return normalized[:77].rstrip() + "..."
