from __future__ import annotations

import json
import re
from pathlib import Path

from pydantic import ValidationError

from app.clients.llm_client import LLMClient, LLMClientError, LLMInvalidResponseError
from app.models.contracts import (
    CodeReviewDraft,
    CodeReviewFailureReply,
    CodeReviewRequest,
    DiffFileChange,
    ReviewEvidenceReference,
    ReviewEvidenceType,
    ReviewFinding,
    ReviewReplyPayload,
    ReviewResultStatus,
    ReviewRiskLevel,
)


class ReviewService:
    def __init__(
        self,
        llm_client: LLMClient,
        *,
        prompt_path: Path | None = None,
    ) -> None:
        self.llm_client = llm_client
        self.prompt_path = prompt_path or Path(__file__).resolve().parents[2] / "prompts" / "code_review_prompt.md"

    async def review(self, request: CodeReviewRequest) -> ReviewReplyPayload:
        if self._should_return_insufficient_context(request):
            return self._build_insufficient_context_reply(request)

        system_prompt = self._load_system_prompt()
        user_prompt = self._build_user_prompt(request)

        try:
            raw_response = await self.llm_client.generate_structured_summary(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
            review_draft = self._parse_review_response(raw_response)
        except (LLMClientError, LLMInvalidResponseError, ValidationError, ValueError, json.JSONDecodeError):
            return self._build_temporary_failure_reply(request)

        return self._finalize_review(review_draft, request=request)

    def _load_system_prompt(self) -> str:
        return self.prompt_path.read_text(encoding="utf-8").strip()

    def _build_user_prompt(self, request: CodeReviewRequest) -> str:
        ordered_files = self._ordered_files(request.files)
        file_summary = "\n".join(
            f"- {file.file_path} | type={file.change_type} | +{file.additions} -{file.deletions}"
            for file in ordered_files[:12]
        ) or "- none"
        policy_refs = "\n".join(
            f"- {citation.label} | {citation.source_uri} | {citation.snippet}"
            for citation in request.policy_citations
        ) or "- none"
        review_focus = ", ".join(item.value for item in request.focus_areas) or "bug_risk, test_gap"
        patch_overview = self._build_patch_overview(ordered_files)
        patch_excerpt = self._build_patch_excerpt(request, ordered_files)

        return (
            f"review_source_type: {request.source_type.value}\n"
            f"review_source_ref: {request.source_ref}\n"
            f"review_focus_areas: {review_focus}\n"
            f"patch_overview:\n{patch_overview}\n\n"
            f"changed_files:\n{file_summary}\n\n"
            f"policy_refs:\n{policy_refs}\n\n"
            f"patch_excerpt:\n{patch_excerpt}\n"
        )

    def _build_patch_excerpt(self, request: CodeReviewRequest, ordered_files: list[DiffFileChange]) -> str:
        segments: list[str] = []
        for file in ordered_files[:5]:
            segments.append(
                f"FILE: {file.file_path} ({file.change_type}, +{file.additions}, -{file.deletions})"
            )
            for hunk in file.hunks[:2]:
                segments.append(hunk.header)
                segments.append(hunk.snippet)
            segments.append("")

        excerpt = "\n".join(segments).strip()
        if excerpt:
            return excerpt[:4000]
        return request.normalized_patch[:4000]

    def _build_patch_overview(self, ordered_files: list[DiffFileChange]) -> str:
        if not ordered_files:
            return "- no parsed files"

        total_additions = sum(file.additions for file in ordered_files)
        total_deletions = sum(file.deletions for file in ordered_files)
        selected_files = min(len(ordered_files), 5)
        omitted_files = max(0, len(ordered_files) - selected_files)
        lines = [
            f"- changed_files: {len(ordered_files)}",
            f"- total_additions: {total_additions}",
            f"- total_deletions: {total_deletions}",
            f"- selected_files_for_excerpt: {selected_files}",
        ]
        if omitted_files:
            lines.append(f"- omitted_files_from_excerpt: {omitted_files}")
        lines.append("- prioritized_files:")
        for file in ordered_files[:5]:
            lines.append(
                f"  - {file.file_path} | type={file.change_type} | +{file.additions} -{file.deletions}"
            )
        return "\n".join(lines)

    def _parse_review_response(self, raw_response: str) -> CodeReviewDraft:
        cleaned_response = raw_response.strip()
        if cleaned_response.startswith("```"):
            cleaned_response = cleaned_response.strip("`")
            cleaned_response = cleaned_response.removeprefix("json").strip()

        payload = self._normalize_review_payload(json.loads(cleaned_response))
        review_draft = CodeReviewDraft.model_validate(payload)
        if review_draft.status not in {
            ReviewResultStatus.SUCCESS,
            ReviewResultStatus.INSUFFICIENT_CONTEXT,
        }:
            raise ValueError("LLM returned unsupported status for code review")
        return review_draft

    def _normalize_review_payload(self, payload: object) -> dict[str, object]:
        if not isinstance(payload, dict):
            raise ValueError("LLM review payload must be a JSON object")

        normalized_payload = dict(payload)
        status = normalized_payload.get("status")
        if isinstance(status, str):
            normalized_payload["status"] = self._normalize_status(status)

        risk = normalized_payload.get("overall_risk")
        if isinstance(risk, str):
            normalized_payload["overall_risk"] = self._normalize_risk(risk)

        findings = normalized_payload.get("findings")
        if isinstance(findings, list):
            normalized_payload["findings"] = [
                finding
                for item in findings
                if (finding := self._normalize_finding_payload(item)) is not None
            ]

        missing_context = normalized_payload.get("missing_context")
        if isinstance(missing_context, list):
            normalized_payload["missing_context"] = [
                item.strip()
                for item in missing_context
                if isinstance(item, str) and item.strip()
            ]

        if not isinstance(normalized_payload.get("publish_recommendation"), str) or not normalized_payload.get("publish_recommendation", "").strip():
            normalized_payload["publish_recommendation"] = "请先保留为草稿，确认 findings 后再决定是否发布。"

        return normalized_payload

    def _normalize_finding_payload(self, payload: object) -> dict[str, object] | None:
        if not isinstance(payload, dict):
            return None

        title = payload.get("title")
        summary = payload.get("summary")
        severity = payload.get("severity")
        if not isinstance(title, str) or not title.strip():
            return None
        if not isinstance(summary, str) or not summary.strip():
            return None

        normalized: dict[str, object] = {
            "title": title.strip(),
            "severity": self._normalize_risk(severity) if isinstance(severity, str) else ReviewRiskLevel.MEDIUM.value,
            "summary": summary.strip(),
        }

        file_path = payload.get("file_path")
        if isinstance(file_path, str) and file_path.strip():
            normalized["file_path"] = file_path.strip()

        for field_name in ("line_start", "line_end"):
            value = payload.get(field_name)
            if isinstance(value, int) and value > 0:
                normalized[field_name] = value

        evidence = payload.get("evidence")
        if isinstance(evidence, list):
            normalized["evidence"] = [
                evidence_item
                for item in evidence
                if (evidence_item := self._normalize_evidence_payload(item)) is not None
            ]

        return normalized

    def _normalize_evidence_payload(self, payload: object) -> dict[str, object] | None:
        if isinstance(payload, str):
            normalized = payload.strip()
            if not normalized:
                return None
            return {
                "evidence_type": ReviewEvidenceType.DIFF_HUNK.value,
                "label": "diff evidence",
                "source_uri": normalized,
                "snippet": normalized,
            }

        if not isinstance(payload, dict):
            return None

        label = payload.get("label")
        source_uri = payload.get("source_uri")
        snippet = payload.get("snippet")
        if not all(isinstance(item, str) and item.strip() for item in (label, source_uri, snippet)):
            return None

        evidence_type = payload.get("evidence_type")
        if isinstance(evidence_type, str):
            normalized_type = self._normalize_evidence_type(evidence_type)
        else:
            normalized_type = ReviewEvidenceType.DIFF_HUNK.value

        return {
            "evidence_type": normalized_type,
            "label": label.strip(),
            "source_uri": source_uri.strip(),
            "snippet": snippet.strip(),
        }

    def _normalize_status(self, status: str) -> str:
        normalized = status.strip().lower()
        status_map = {
            "success": ReviewResultStatus.SUCCESS.value,
            "analysis_complete": ReviewResultStatus.SUCCESS.value,
            "needs_more_info": ReviewResultStatus.INSUFFICIENT_CONTEXT.value,
            "need_more_info": ReviewResultStatus.INSUFFICIENT_CONTEXT.value,
            "insufficient_context": ReviewResultStatus.INSUFFICIENT_CONTEXT.value,
        }
        return status_map.get(normalized, normalized)

    def _normalize_risk(self, risk: str) -> str:
        normalized = risk.strip().lower()
        risk_map = {
            "low": ReviewRiskLevel.LOW.value,
            "medium": ReviewRiskLevel.MEDIUM.value,
            "moderate": ReviewRiskLevel.MEDIUM.value,
            "high": ReviewRiskLevel.HIGH.value,
            "critical": ReviewRiskLevel.HIGH.value,
        }
        return risk_map.get(normalized, ReviewRiskLevel.MEDIUM.value)

    def _normalize_evidence_type(self, evidence_type: str) -> str:
        normalized = evidence_type.strip().lower()
        evidence_map = {
            "diff_hunk": ReviewEvidenceType.DIFF_HUNK.value,
            "diff": ReviewEvidenceType.DIFF_HUNK.value,
            "policy_doc": ReviewEvidenceType.POLICY_DOC.value,
            "policy": ReviewEvidenceType.POLICY_DOC.value,
            "github_pr": ReviewEvidenceType.GITHUB_PR.value,
            "pr": ReviewEvidenceType.GITHUB_PR.value,
        }
        return evidence_map.get(normalized, ReviewEvidenceType.DIFF_HUNK.value)

    def _should_return_insufficient_context(self, request: CodeReviewRequest) -> bool:
        if not request.normalized_patch.strip():
            return True
        return len(request.files) == 0

    def _ordered_files(self, files: list[DiffFileChange]) -> list[DiffFileChange]:
        return sorted(files, key=self._file_sort_key)

    def _file_sort_key(self, file: DiffFileChange) -> tuple[int, int, str]:
        return (
            -self._file_priority(file),
            -(file.additions + file.deletions),
            file.file_path.lower(),
        )

    def _file_priority(self, file: DiffFileChange) -> int:
        path = file.file_path.replace("\\", "/").lower()
        score = file.additions + file.deletions

        if file.change_type in {"added", "deleted", "renamed"}:
            score += 20
        if any(keyword in path for keyword in ("auth", "security", "permission", "token", "session")):
            score += 50
        if any(keyword in path for keyword in ("test", "tests", "spec")):
            score += 40
        if any(keyword in path for keyword in ("api", "service", "handler", "controller", "router", "middleware")):
            score += 10

        return score

    def _finalize_review(
        self,
        review_draft: CodeReviewDraft,
        *,
        request: CodeReviewRequest,
    ) -> CodeReviewDraft:
        findings: list[ReviewFinding] = []
        for index, finding in enumerate(review_draft.findings, start=1):
            update: dict[str, object] = {
                "finding_id": finding.finding_id or f"F{index}",
                "focus_areas": finding.focus_areas or request.focus_areas,
            }
            if not finding.evidence:
                update["evidence"] = self._build_diff_evidence_for_finding(
                    request=request,
                    finding=finding,
                )
            findings.append(finding.model_copy(update=update))

        if review_draft.status is ReviewResultStatus.SUCCESS and not findings:
            updated_missing_context = list(review_draft.missing_context)
            publish_recommendation = "当前未发现高置信问题，建议先以草稿形式回传，不直接发布外部评论。"
        else:
            updated_missing_context = review_draft.missing_context
            publish_recommendation = review_draft.publish_recommendation

        return review_draft.model_copy(
            update={
                "focus_areas": request.focus_areas,
                "findings": findings,
                "publish_recommendation": publish_recommendation,
                "missing_context": updated_missing_context,
            }
        )

    def _build_diff_evidence_for_finding(
        self,
        *,
        request: CodeReviewRequest,
        finding: ReviewFinding,
    ) -> list[ReviewEvidenceReference]:
        if not finding.file_path:
            return []

        normalized_target = finding.file_path.replace("\\", "/").strip()
        for file in request.files:
            if file.file_path.replace("\\", "/").strip() != normalized_target:
                continue

            if file.hunks:
                best_hunk = self._select_best_hunk(file=file, finding=finding)
                if best_hunk is None:
                    best_hunk = file.hunks[0]
                return [
                    ReviewEvidenceReference(
                        evidence_type=ReviewEvidenceType.DIFF_HUNK,
                        label=f"{file.file_path} {best_hunk.header}",
                        source_uri=f"{request.source_ref}#{file.file_path}",
                        snippet=best_hunk.snippet,
                    )
                ]
            return [
                ReviewEvidenceReference(
                    evidence_type=ReviewEvidenceType.DIFF_HUNK,
                    label=file.file_path,
                    source_uri=f"{request.source_ref}#{file.file_path}",
                    snippet=f"file change summary: +{file.additions} -{file.deletions}",
                )
            ]
        return []

    def _select_best_hunk(self, *, file: DiffFileChange, finding: ReviewFinding):
        tokens = self._extract_relevance_tokens(
            " ".join(
                part
                for part in (
                    finding.title,
                    finding.summary,
                    finding.file_path or "",
                )
                if part
            )
        )
        if not tokens:
            return None

        best_hunk = None
        best_score = 0
        for hunk in file.hunks:
            hunk_text = f"{hunk.header} {hunk.snippet}".lower()
            score = sum(1 for token in tokens if token in hunk_text)
            if score > best_score:
                best_score = score
                best_hunk = hunk
        return best_hunk

    def _extract_relevance_tokens(self, text: str) -> set[str]:
        return {
            token.lower()
            for token in re.findall(r"[A-Za-z0-9_]+", text)
            if len(token) >= 3
        }

    def _build_insufficient_context_reply(self, request: CodeReviewRequest) -> CodeReviewDraft:
        return CodeReviewDraft(
            status=ReviewResultStatus.INSUFFICIENT_CONTEXT,
            overall_assessment="当前无法形成可靠的代码审查结论。",
            overall_risk=ReviewRiskLevel.LOW,
            focus_areas=request.focus_areas,
            findings=[],
            missing_context=[
                "可解析的 diff/patch 内容",
                *(["GitHub PR patch 获取结果"] if request.source_type.value == "github_pr" else []),
            ],
            publish_recommendation="请补充 patch/diff，或确保机器人能访问对应 PR 后再重试。",
        )

    def _build_temporary_failure_reply(self, request: CodeReviewRequest) -> CodeReviewFailureReply:
        return CodeReviewFailureReply(
            status=ReviewResultStatus.TEMPORARY_FAILURE,
            headline="本次代码审查未完整完成",
            known_limits=[
                f"review_source={request.source_type.value}",
                f"changed_files={len(request.files)}",
            ],
            missing_context=["完整的 review 输出"],
            retry_hint="请稍后重试，或缩小 diff 范围后再次触发。",
        )
