from __future__ import annotations

from app.services.retrieval.models import (
    LoadedKnowledgeDocument,
    RetrievalRoute,
    RoutedDocument,
)


RELEASE_ROUTE_HINTS = ("release", "deploy", "rollback", "regression", "发布", "回滚")
POLICY_ROUTE_HINTS = ("policy", "checklist", "task-sync", "template", "approval", "sync")
RUNBOOK_ROUTE_HINTS = ("runbook", "playbook", "sop", "guide", "auth")


class RetrievalRouter:
    def route_documents(
        self,
        documents: list[LoadedKnowledgeDocument],
    ) -> list[RoutedDocument]:
        return [
            RoutedDocument(document=document, route=self._classify_route(document))
            for document in documents
        ]

    def _classify_route(self, document: LoadedKnowledgeDocument) -> RetrievalRoute:
        route_text = " ".join(
            [
                document.metadata.doc_id,
                document.metadata.title,
                document.metadata.path,
                *document.metadata.tags,
            ]
        ).lower()

        if any(hint in route_text for hint in RELEASE_ROUTE_HINTS):
            return RetrievalRoute.RELEASE_NOTES
        if any(hint in route_text for hint in POLICY_ROUTE_HINTS):
            return RetrievalRoute.POLICY
        if any(hint in route_text for hint in RUNBOOK_ROUTE_HINTS):
            return RetrievalRoute.RUNBOOK
        return RetrievalRoute.GENERAL
