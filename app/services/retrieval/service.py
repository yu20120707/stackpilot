from __future__ import annotations

from typing import Callable

from app.models.contracts import AnalysisRequest, KnowledgeCitation, SourceType
from app.services.retrieval.models import LoadedKnowledgeDocument
from app.services.retrieval.planner import RetrievalPlanner
from app.services.retrieval.ranker import EvidenceRanker
from app.services.retrieval.router import RetrievalRouter


class RetrievalService:
    def __init__(
        self,
        *,
        document_loader: Callable[[], list[LoadedKnowledgeDocument]],
        default_max_hits: int = 5,
        planner: RetrievalPlanner | None = None,
        router: RetrievalRouter | None = None,
        ranker: EvidenceRanker | None = None,
    ) -> None:
        self.document_loader = document_loader
        self.default_max_hits = default_max_hits
        self.planner = planner or RetrievalPlanner()
        self.router = router or RetrievalRouter()
        self.ranker = ranker or EvidenceRanker()

    def retrieve(
        self,
        analysis_request: AnalysisRequest,
        *,
        max_hits: int | None = None,
    ) -> list[KnowledgeCitation]:
        plan = self.planner.plan(analysis_request)
        if not plan.query_terms:
            return []

        routed_documents = self.router.route_documents(self.document_loader())
        limit = max_hits or self.default_max_hits
        evidence = self.ranker.rank(plan, routed_documents, max_hits=limit)

        if not evidence:
            second_pass_plan = self.planner.build_second_pass_plan(plan)
            if second_pass_plan is not None:
                evidence = self.ranker.rank(second_pass_plan, routed_documents, max_hits=limit)

        return [
            KnowledgeCitation(
                source_type=SourceType.KNOWLEDGE_DOC,
                label=item.document.metadata.title,
                source_uri=item.document.metadata.path,
                snippet=item.snippet or item.document.metadata.path,
            )
            for item in evidence
        ]
