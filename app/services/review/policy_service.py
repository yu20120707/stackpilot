from __future__ import annotations

from app.models.contracts import (
    CanonicalPolicyScope,
    CodeReviewRequest,
    KnowledgeCitation,
    ReviewFocusArea,
    SourceType,
)
from app.services.knowledge_base import KnowledgeBase


BASE_POLICY_KEYWORDS = ("review", "policy", "代码审查", "code review")
FOCUS_KEYWORDS: dict[ReviewFocusArea, tuple[str, ...]] = {
    ReviewFocusArea.BUG_RISK: ("bug", "risk", "regression", "回归", "异常", "defect"),
    ReviewFocusArea.TEST_GAP: ("test", "coverage", "测试", "单测", "integration"),
    ReviewFocusArea.SECURITY: ("security", "secure", "auth", "安全", "权限", "注入"),
}


class ReviewPolicyService:
    def __init__(self, knowledge_base: KnowledgeBase, *, max_hits: int = 2) -> None:
        self.knowledge_base = knowledge_base
        self.max_hits = max_hits

    def retrieve_policy_citations(self, request: CodeReviewRequest) -> list[KnowledgeCitation]:
        scored_documents: list[tuple[int, object]] = []
        request_terms = {
            segment.lower()
            for file in request.files
            for segment in file.file_path.replace("\\", "/").split("/")
            if segment
        }

        for document in self.knowledge_base.load_documents_for_tenant(
            request.chat_id,
            use_case=CanonicalPolicyScope.REVIEW,
        ):
            haystack = " ".join(
                [
                    document.metadata.title.lower(),
                    document.metadata.path.lower(),
                    " ".join(tag.lower() for tag in document.metadata.tags),
                    document.content[:500].lower(),
                ]
            )
            score = sum(2 for keyword in BASE_POLICY_KEYWORDS if keyword in haystack)
            for focus_area in request.focus_areas:
                score += sum(3 for keyword in FOCUS_KEYWORDS.get(focus_area, ()) if keyword in haystack)
            score += sum(1 for term in request_terms if term and term in haystack)
            if score <= 0:
                continue
            scored_documents.append((score, document))

        scored_documents.sort(key=lambda item: item[0], reverse=True)
        citations: list[KnowledgeCitation] = []
        for _, document in scored_documents[: self.max_hits]:
            citations.append(
                KnowledgeCitation(
                    source_type=SourceType.KNOWLEDGE_DOC,
                    label=document.metadata.title,
                    source_uri=document.metadata.path,
                    snippet=document.content[:160].strip() or document.metadata.path,
                )
            )
        return citations
