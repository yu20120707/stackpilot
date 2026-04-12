from __future__ import annotations

from app.services.retrieval.models import (
    RetrievalPlan,
    RetrievalRoute,
    RetrievedEvidence,
    RoutedDocument,
)
from app.services.retrieval.utils import build_snippet


class EvidenceRanker:
    def __init__(self, min_score_threshold: int = 14) -> None:
        self.min_score_threshold = min_score_threshold

    def rank(
        self,
        plan: RetrievalPlan,
        routed_documents: list[RoutedDocument],
        *,
        max_hits: int,
    ) -> list[RetrievedEvidence]:
        scored_evidence: list[RetrievedEvidence] = []

        for routed_document in routed_documents:
            evidence = self._score_document(plan, routed_document)
            if evidence is not None:
                scored_evidence.append(evidence)

        scored_evidence.sort(
            key=lambda item: (
                -item.score,
                item.document.metadata.title.lower(),
                item.document.metadata.path,
            )
        )
        return scored_evidence[:max_hits]

    def _score_document(
        self,
        plan: RetrievalPlan,
        routed_document: RoutedDocument,
    ) -> RetrievedEvidence | None:
        document = routed_document.document
        normalized_content = document.content.lower()
        metadata_terms = [
            document.metadata.doc_id,
            document.metadata.title,
            document.metadata.path,
            *document.metadata.tags,
        ]
        normalized_metadata = " ".join(metadata_terms).lower()

        matched_terms = tuple(
            sorted(
                {
                    term
                    for term in plan.query_terms
                    if term in normalized_content or term in normalized_metadata
                }
            )
        )
        if not matched_terms:
            return None

        overlap_score = sum(min(len(term), 8) for term in matched_terms)
        metadata_bonus = sum(
            5 for term in matched_terms if term in normalized_metadata
        )
        route_bonus = self._route_bonus(
            route=routed_document.route,
            preferred_routes=plan.preferred_routes,
        )
        phrase_bonus = self._phrase_bonus(
            route=routed_document.route,
            normalized_content=normalized_content,
            matched_terms=matched_terms,
        )
        score = overlap_score + metadata_bonus + route_bonus + phrase_bonus
        if score < self.min_score_threshold:
            return None

        best_term = min(
            matched_terms,
            key=lambda term: self._term_priority(
                term=term,
                normalized_metadata=normalized_metadata,
                normalized_content=normalized_content,
            ),
        )
        return RetrievedEvidence(
            document=document,
            route=routed_document.route,
            score=score,
            matched_terms=matched_terms,
            best_term=best_term,
            snippet=build_snippet(document.content, best_term),
        )

    def _route_bonus(
        self,
        *,
        route: RetrievalRoute,
        preferred_routes: tuple[RetrievalRoute, ...],
    ) -> int:
        if route is RetrievalRoute.GENERAL:
            return 0
        if route not in preferred_routes:
            return 0
        route_index = preferred_routes.index(route)
        return max(0, 24 - route_index * 8)

    def _phrase_bonus(
        self,
        *,
        route: RetrievalRoute,
        normalized_content: str,
        matched_terms: tuple[str, ...],
    ) -> int:
        bonus = 0
        if route is RetrievalRoute.RELEASE_NOTES and any(
            term in matched_terms for term in ("release", "deploy", "rollback")
        ):
            bonus += 6
        if route is RetrievalRoute.RUNBOOK and any(
            term in matched_terms for term in ("auth", "login", "log", "日志")
        ):
            bonus += 4
        if route is RetrievalRoute.POLICY and any(
            term in matched_terms for term in ("policy", "checklist", "task-sync", "approval")
        ):
            bonus += 4
        if "5xx" in normalized_content and "5xx" in matched_terms:
            bonus += 2
        return bonus

    def _term_priority(
        self,
        *,
        term: str,
        normalized_metadata: str,
        normalized_content: str,
    ) -> tuple[int, int, int]:
        metadata_index = normalized_metadata.find(term)
        content_index = normalized_content.find(term)
        normalized_metadata_index = metadata_index if metadata_index >= 0 else 10_000
        normalized_content_index = content_index if content_index >= 0 else 10_000
        return (normalized_metadata_index, normalized_content_index, -len(term))
