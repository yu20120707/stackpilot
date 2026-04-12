from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from app.clients.llm_client import LLMClient, LLMClientError, LLMInvalidResponseError
from app.models.contracts import (
    AnalysisRequest,
    OrgPostmortemStyle,
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
        self.prompt_path = prompt_path or Path(__file__).resolve().parents[2] / "prompts" / "postmortem_prompt.md"

    async def generate_draft(
        self,
        *,
        request: AnalysisRequest,
        summary: StructuredSummary,
        org_style: OrgPostmortemStyle | None = None,
    ) -> PostmortemDraft:
        system_prompt = self._load_system_prompt()
        user_prompt = self._build_user_prompt(
            request=request,
            summary=summary,
            org_style=org_style,
        )

        try:
            raw_response = await self.llm_client.generate_structured_summary(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
            draft = self._parse_draft_response(raw_response)
        except (LLMClientError, LLMInvalidResponseError, ValidationError, ValueError, json.JSONDecodeError):
            draft = self._build_fallback_draft(
                request=request,
                summary=summary,
                org_style=org_style,
            )
        if org_style is not None:
            draft = self._apply_org_style(draft, org_style=org_style)

        return draft.model_copy(update={"citations": summary.citations})

    def _load_system_prompt(self) -> str:
        return self.prompt_path.read_text(encoding="utf-8").strip()

    def _build_user_prompt(
        self,
        *,
        request: AnalysisRequest,
        summary: StructuredSummary,
        org_style: OrgPostmortemStyle | None,
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
        style_block = self._build_style_prompt_block(org_style)

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
            f"{style_block}"
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
        org_style: OrgPostmortemStyle | None,
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

    def _build_style_prompt_block(self, org_style: OrgPostmortemStyle | None) -> str:
        if org_style is None:
            return ""

        style_lines = ["", "postmortem_style:"]
        if org_style.template_name:
            style_lines.append(f"- template_name: {org_style.template_name}")
        if org_style.title_prefix:
            style_lines.append(f"- title_prefix: {org_style.title_prefix}")
        if org_style.follow_up_prefix:
            style_lines.append(f"- follow_up_prefix: {org_style.follow_up_prefix}")
        if org_style.section_labels:
            style_lines.append(
                f"- section_labels: {json.dumps(org_style.section_labels, ensure_ascii=False)}"
            )
        return "\n".join(style_lines) + "\n"

    def _apply_org_style(
        self,
        draft: PostmortemDraft,
        *,
        org_style: OrgPostmortemStyle,
    ) -> PostmortemDraft:
        title = draft.title
        if org_style.title_prefix and not title.startswith(org_style.title_prefix):
            title = f"{org_style.title_prefix} {title}".strip()

        follow_up_actions = draft.follow_up_actions
        if org_style.follow_up_prefix:
            follow_up_actions = [
                action
                if action.startswith(org_style.follow_up_prefix)
                else f"{org_style.follow_up_prefix}{action}"
                for action in draft.follow_up_actions
            ]

        return draft.model_copy(
            update={
                "title": title,
                "follow_up_actions": follow_up_actions,
            }
        )

    def _build_title(self, summary: StructuredSummary) -> str:
        base_title = summary.conclusion_summary or summary.current_assessment
        normalized = " ".join(base_title.split())
        if len(normalized) <= 80:
            return normalized
        return normalized[:77].rstrip() + "..."
