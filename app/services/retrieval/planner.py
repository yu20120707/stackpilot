from __future__ import annotations

from app.models.contracts import AnalysisRequest
from app.services.retrieval.models import RetrievalPlan, RetrievalRoute
from app.services.retrieval.utils import extract_terms


RELEASE_HINTS = ("release", "deploy", "deployment", "rollback", "变更", "发布", "回滚")
RUNBOOK_HINTS = ("runbook", "playbook", "sop", "auth", "login", "日志", "log", "错误")
POLICY_HINTS = ("policy", "checklist", "task", "sync", "approval", "confirm", "确认", "待办")

ROUTE_EXPANSIONS: dict[RetrievalRoute, tuple[str, ...]] = {
    RetrievalRoute.RELEASE_NOTES: ("release", "deploy", "rollback", "change"),
    RetrievalRoute.RUNBOOK: ("runbook", "sop", "log", "error"),
    RetrievalRoute.POLICY: ("policy", "checklist", "task-sync", "approval"),
    RetrievalRoute.GENERAL: (),
}


class RetrievalPlanner:
    def plan(self, analysis_request: AnalysisRequest) -> RetrievalPlan:
        query_text = "\n".join(message.text for message in analysis_request.thread_messages)
        lowered_query = query_text.lower()
        query_terms = extract_terms(query_text)

        preferred_routes: list[RetrievalRoute] = []
        if self._contains_any(lowered_query, RELEASE_HINTS):
            preferred_routes.append(RetrievalRoute.RELEASE_NOTES)
        if self._contains_any(lowered_query, RUNBOOK_HINTS):
            preferred_routes.append(RetrievalRoute.RUNBOOK)
        if self._contains_any(lowered_query, POLICY_HINTS):
            preferred_routes.append(RetrievalRoute.POLICY)
        if not preferred_routes:
            preferred_routes.append(RetrievalRoute.GENERAL)

        expansion_terms = tuple(
            term
            for route in preferred_routes
            for term in ROUTE_EXPANSIONS.get(route, ())
            if term not in query_terms
        )

        return RetrievalPlan(
            query_text=query_text,
            query_terms=query_terms,
            preferred_routes=tuple(preferred_routes),
            expansion_terms=expansion_terms,
            allow_second_pass=bool(expansion_terms),
        )

    def build_second_pass_plan(self, plan: RetrievalPlan) -> RetrievalPlan | None:
        if not plan.allow_second_pass or not plan.expansion_terms:
            return None

        expanded_terms = set(plan.query_terms)
        expanded_terms.update(plan.expansion_terms)
        return RetrievalPlan(
            query_text=plan.query_text,
            query_terms=expanded_terms,
            preferred_routes=plan.preferred_routes,
            expansion_terms=(),
            allow_second_pass=False,
        )

    def _contains_any(self, text: str, hints: tuple[str, ...]) -> bool:
        return any(hint in text for hint in hints)
