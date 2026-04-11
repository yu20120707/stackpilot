from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from app.core.logging import get_logger
from app.models.contracts import (
    CanonicalConventionDocument,
    CanonicalConventionStatus,
    CanonicalPolicyScope,
    KnowledgeDocumentMetadata,
    OrgPostmortemStyle,
    OrgReviewDefaults,
)
from app.services.retrieval.models import LoadedKnowledgeDocument


logger = get_logger(__name__)


class CanonicalConventionService:
    def __init__(self, knowledge_dir: Path) -> None:
        self.knowledge_dir = knowledge_dir

    def load_review_defaults(self, tenant_id: str) -> OrgReviewDefaults | None:
        resolved_defaults: OrgReviewDefaults | None = None
        for document in self._load_approved_documents(tenant_id):
            defaults = document.review_defaults
            if defaults is not None and defaults.default_focus_areas:
                resolved_defaults = defaults
        return resolved_defaults

    def load_postmortem_style(self, tenant_id: str) -> OrgPostmortemStyle | None:
        payload: dict[str, object] = {}
        section_labels: dict[str, str] = {}

        for document in self._load_approved_documents(tenant_id):
            style = document.postmortem_style
            if style is None:
                continue
            if style.template_name:
                payload["template_name"] = style.template_name
            if style.title_prefix:
                payload["title_prefix"] = style.title_prefix
            if style.follow_up_prefix:
                payload["follow_up_prefix"] = style.follow_up_prefix
            if style.section_labels:
                section_labels.update(style.section_labels)

        if section_labels:
            payload["section_labels"] = section_labels
        if not payload:
            return None
        return OrgPostmortemStyle.model_validate(payload)

    def load_policy_documents(
        self,
        tenant_id: str,
        *,
        use_case: CanonicalPolicyScope | None = None,
    ) -> list[LoadedKnowledgeDocument]:
        loaded_documents: list[LoadedKnowledgeDocument] = []
        for document in self._load_approved_documents(tenant_id):
            for policy_document in document.policy_documents:
                if use_case is not None and policy_document.scope not in {
                    use_case,
                    CanonicalPolicyScope.SHARED,
                }:
                    continue
                source_uri = (
                    policy_document.source_uri
                    or f"canonical://{tenant_id}/{document.convention_id}/{policy_document.doc_id}"
                )
                tags = self._dedupe_tags(
                    [
                        "canonical",
                        "approved",
                        f"tenant:{tenant_id}",
                        f"scope:{policy_document.scope.value}",
                        *policy_document.tags,
                    ]
                )
                loaded_documents.append(
                    LoadedKnowledgeDocument(
                        metadata=KnowledgeDocumentMetadata(
                            doc_id=policy_document.doc_id,
                            title=policy_document.title,
                            path=source_uri,
                            tags=tags,
                        ),
                        content=policy_document.content,
                    )
                )
        return loaded_documents

    def _load_approved_documents(self, tenant_id: str) -> list[CanonicalConventionDocument]:
        tenant_dir = self.knowledge_dir / "canonical" / tenant_id
        if not tenant_dir.exists():
            return []

        documents: list[CanonicalConventionDocument] = []
        for path in sorted(tenant_dir.glob("*.canonical.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                document = CanonicalConventionDocument.model_validate(payload)
            except (OSError, ValueError, TypeError, json.JSONDecodeError, ValidationError):
                logger.warning("Skipping unreadable canonical convention file: %s", path)
                continue
            if document.status is not CanonicalConventionStatus.APPROVED:
                continue
            documents.append(document)
        return documents

    def _dedupe_tags(self, tags: list[str]) -> list[str]:
        unique_tags: list[str] = []
        for tag in tags:
            normalized = tag.strip()
            if normalized and normalized not in unique_tags:
                unique_tags.append(normalized)
        return unique_tags[:8]
