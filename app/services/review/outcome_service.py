from __future__ import annotations

from datetime import datetime, timezone
import re

from app.clients.github_review_client import GitHubIssueComment, GitHubReviewClient
from app.models.contracts import (
    ReviewFeedbackStatus,
    ReviewMemoryState,
    ReviewOutcomeIngestResult,
    ReviewOutcomeSignal,
    ReviewOutcomeSource,
    ReviewOutcomeStatus,
    ReviewPublishResult,
)


FINDING_ID_PATTERN = re.compile(r"\bF\d+\b", re.IGNORECASE)
ACCEPTED_KEYWORDS = (
    "fixed",
    "addressed",
    "resolved",
    "done",
    "agree",
    "accepted",
    "已修复",
    "已处理",
    "已解决",
    "已采纳",
)
IGNORED_KEYWORDS = (
    "ignore",
    "ignored",
    "won't fix",
    "wont fix",
    "not fix",
    "false positive",
    "not applicable",
    "by design",
    "暂不修复",
    "不修复",
    "误报",
    "忽略",
    "不处理",
)


class ReviewOutcomeService:
    def __init__(self, github_review_client: GitHubReviewClient) -> None:
        self.github_review_client = github_review_client

    def apply_publish_result(
        self,
        *,
        review_state: ReviewMemoryState,
        publish_result: ReviewPublishResult,
        observed_at: datetime | None = None,
    ) -> tuple[ReviewMemoryState, list[ReviewOutcomeSignal]]:
        if publish_result.status.value != "published" or not publish_result.published_ref:
            return review_state, []

        observed_at = observed_at or datetime.now(timezone.utc)
        updated_findings = []
        signals: list[ReviewOutcomeSignal] = []
        published_at = publish_result.published_at or observed_at
        for finding in review_state.findings:
            updated_findings.append(
                finding.model_copy(
                    update={
                        "outcome_status": ReviewOutcomeStatus.PUBLISHED,
                        "outcome_source": ReviewOutcomeSource.GITHUB_PUBLISH,
                        "outcome_source_ref": publish_result.published_ref,
                        "outcome_recorded_at": published_at,
                    }
                )
            )
            signals.append(
                ReviewOutcomeSignal(
                    finding_id=finding.finding_id,
                    status=ReviewOutcomeStatus.PUBLISHED,
                    source=ReviewOutcomeSource.GITHUB_PUBLISH,
                    source_ref=publish_result.published_ref,
                    observed_at=published_at,
                )
            )

        next_state = review_state.model_copy(
            update={
                "findings": updated_findings,
                "published_review_ref": publish_result.published_ref,
                "published_review_comment_id": publish_result.published_comment_id,
                "published_at": published_at,
                "updated_at": observed_at,
            }
        )

        if not signals:
            signals.append(
                ReviewOutcomeSignal(
                    status=ReviewOutcomeStatus.PUBLISHED,
                    source=ReviewOutcomeSource.GITHUB_PUBLISH,
                    source_ref=publish_result.published_ref,
                    observed_at=published_at,
                    note="review_published_without_findings",
                )
            )
        return next_state, signals

    def apply_explicit_feedback(
        self,
        *,
        review_state: ReviewMemoryState,
        finding_id: str,
        feedback_status: ReviewFeedbackStatus,
        observed_at: datetime | None = None,
    ) -> tuple[ReviewMemoryState, object | None, ReviewOutcomeSignal | None]:
        observed_at = observed_at or datetime.now(timezone.utc)
        outcome_status = (
            ReviewOutcomeStatus.ACCEPTED
            if feedback_status is ReviewFeedbackStatus.ACCEPTED
            else ReviewOutcomeStatus.IGNORED
        )

        updated_findings = []
        target_finding = None
        signal: ReviewOutcomeSignal | None = None
        for finding in review_state.findings:
            if (finding.finding_id or "").upper() != finding_id.upper():
                updated_findings.append(finding)
                continue

            target_finding = finding.model_copy(
                update={
                    "feedback_status": feedback_status,
                    "feedback_recorded_at": observed_at,
                    "outcome_status": outcome_status,
                    "outcome_source": ReviewOutcomeSource.FEISHU_FEEDBACK,
                    "outcome_source_ref": review_state.source_ref,
                    "outcome_recorded_at": observed_at,
                }
            )
            updated_findings.append(target_finding)
            signal = ReviewOutcomeSignal(
                finding_id=target_finding.finding_id,
                status=outcome_status,
                source=ReviewOutcomeSource.FEISHU_FEEDBACK,
                source_ref=review_state.source_ref,
                observed_at=observed_at,
            )

        if target_finding is None:
            return review_state, None, None

        next_state = review_state.model_copy(
            update={
                "findings": updated_findings,
                "updated_at": observed_at,
            }
        )
        return next_state, target_finding, signal

    async def ingest_github_outcomes(
        self,
        *,
        review_state: ReviewMemoryState,
        observed_at: datetime | None = None,
    ) -> tuple[ReviewMemoryState, ReviewOutcomeIngestResult]:
        observed_at = observed_at or datetime.now(timezone.utc)
        if not review_state.published_review_ref:
            return review_state, ReviewOutcomeIngestResult(
                source_ref=review_state.source_ref,
                message="review_not_published",
            )

        comments = await self.github_review_client.list_issue_comments(
            pull_request_url=review_state.source_ref,
        )
        known_finding_ids = {
            (finding.finding_id or "").upper()
            for finding in review_state.findings
            if finding.finding_id
        }
        explicit_signals = self._extract_comment_signals(
            comments=comments,
            review_state=review_state,
            known_finding_ids=known_finding_ids,
        )

        updated_findings = []
        recorded_signals: list[ReviewOutcomeSignal] = []
        latest_signals = {
            (signal.finding_id or "").upper(): signal
            for signal in explicit_signals
            if signal.finding_id
        }
        for finding in review_state.findings:
            finding_key = (finding.finding_id or "").upper()
            explicit_signal = latest_signals.get(finding_key)
            if explicit_signal is not None and finding.feedback_status is None:
                next_finding = finding.model_copy(
                    update={
                        "outcome_status": explicit_signal.status,
                        "outcome_source": explicit_signal.source,
                        "outcome_source_ref": explicit_signal.source_ref,
                        "outcome_recorded_at": explicit_signal.observed_at,
                    }
                )
                updated_findings.append(next_finding)
                if self._should_record_signal(finding, explicit_signal):
                    recorded_signals.append(explicit_signal)
                continue

            unresolved_signal = ReviewOutcomeSignal(
                finding_id=finding.finding_id,
                status=ReviewOutcomeStatus.UNRESOLVED,
                source=ReviewOutcomeSource.GITHUB_SYNC,
                source_ref=review_state.published_review_ref,
                observed_at=observed_at,
            )
            if self._should_mark_unresolved(finding):
                next_finding = finding.model_copy(
                    update={
                        "outcome_status": ReviewOutcomeStatus.UNRESOLVED,
                        "outcome_source": ReviewOutcomeSource.GITHUB_SYNC,
                        "outcome_source_ref": review_state.published_review_ref,
                        "outcome_recorded_at": observed_at,
                    }
                )
                updated_findings.append(next_finding)
                recorded_signals.append(unresolved_signal)
                continue

            updated_findings.append(finding)

        next_state = review_state.model_copy(
            update={
                "findings": updated_findings,
                "last_outcome_sync_at": observed_at,
                "updated_at": observed_at,
            }
        )
        return next_state, ReviewOutcomeIngestResult(
            source_ref=review_state.source_ref,
            published_ref=review_state.published_review_ref,
            scanned_comment_count=len(comments),
            signals=recorded_signals,
            message="github_review_outcomes_synced",
        )

    def _extract_comment_signals(
        self,
        *,
        comments: list[GitHubIssueComment],
        review_state: ReviewMemoryState,
        known_finding_ids: set[str],
    ) -> list[ReviewOutcomeSignal]:
        relevant_comments = [
            comment
            for comment in comments
            if self._is_comment_relevant(comment, review_state)
        ]
        relevant_comments.sort(
            key=lambda item: item.created_at or datetime.min.replace(tzinfo=timezone.utc)
        )

        signals: list[ReviewOutcomeSignal] = []
        for comment in relevant_comments:
            outcome_status = self._classify_comment_status(comment.body)
            if outcome_status is None:
                continue

            finding_ids = {
                match.group(0).upper()
                for match in FINDING_ID_PATTERN.finditer(comment.body)
                if match.group(0).upper() in known_finding_ids
            }
            if not finding_ids:
                continue

            for finding_id in sorted(finding_ids):
                signals.append(
                    ReviewOutcomeSignal(
                        finding_id=finding_id,
                        status=outcome_status,
                        source=ReviewOutcomeSource.GITHUB_COMMENT,
                        source_ref=comment.html_url,
                        observed_at=comment.created_at or datetime.now(timezone.utc),
                    )
                )
        return signals

    def _is_comment_relevant(
        self,
        comment: GitHubIssueComment,
        review_state: ReviewMemoryState,
    ) -> bool:
        if (
            review_state.published_review_comment_id is not None
            and comment.comment_id == review_state.published_review_comment_id
        ):
            return False
        if (
            review_state.published_at is not None
            and comment.created_at is not None
            and comment.created_at < review_state.published_at
        ):
            return False
        return True

    def _classify_comment_status(self, body: str) -> ReviewOutcomeStatus | None:
        normalized = body.lower()
        has_accepted = any(keyword in normalized for keyword in ACCEPTED_KEYWORDS)
        has_ignored = any(keyword in normalized for keyword in IGNORED_KEYWORDS)
        if has_accepted and not has_ignored:
            return ReviewOutcomeStatus.ACCEPTED
        if has_ignored and not has_accepted:
            return ReviewOutcomeStatus.IGNORED
        return None

    def _should_mark_unresolved(self, finding) -> bool:
        if finding.feedback_status is not None:
            return False
        return finding.outcome_status not in {
            ReviewOutcomeStatus.ACCEPTED,
            ReviewOutcomeStatus.IGNORED,
            ReviewOutcomeStatus.UNRESOLVED,
        }

    def _should_record_signal(self, finding, signal: ReviewOutcomeSignal) -> bool:
        return not (
            finding.outcome_status is signal.status
            and finding.outcome_source is signal.source
            and finding.outcome_source_ref == signal.source_ref
        )
