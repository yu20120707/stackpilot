from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.models.contracts import KnowledgeDocumentMetadata


@dataclass(slots=True)
class LoadedKnowledgeDocument:
    metadata: KnowledgeDocumentMetadata
    content: str


class RetrievalRoute(str, Enum):
    RELEASE_NOTES = "release_notes"
    RUNBOOK = "runbook"
    POLICY = "policy"
    GENERAL = "general"


@dataclass(slots=True)
class RetrievalPlan:
    query_text: str
    query_terms: set[str]
    preferred_routes: tuple[RetrievalRoute, ...]
    expansion_terms: tuple[str, ...]
    allow_second_pass: bool = True


@dataclass(slots=True)
class RoutedDocument:
    document: LoadedKnowledgeDocument
    route: RetrievalRoute


@dataclass(slots=True)
class RetrievedEvidence:
    document: LoadedKnowledgeDocument
    route: RetrievalRoute
    score: int
    matched_terms: tuple[str, ...]
    best_term: str
    snippet: str
