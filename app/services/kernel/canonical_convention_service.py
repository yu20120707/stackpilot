from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from app.core.logging import get_logger
from app.models.contracts import AuditLogEntry
from app.models.contracts import (
    CanonicalConventionDocument,
    CanonicalConventionStatus,
    CanonicalPolicyScope,
    KnowledgeDocumentMetadata,
    OrgPostmortemStyle,
    OrgReviewDefaults,
)
from app.services.kernel.audit_log_service import AuditLogService
from app.services.retrieval.models import LoadedKnowledgeDocument


logger = get_logger(__name__)


class CanonicalConventionService:
    def __init__(
        self,
        knowledge_dir: Path,
        *,
        audit_log_service: AuditLogService | None = None,
    ) -> None:
        self.knowledge_dir = knowledge_dir
        self.audit_log_service = audit_log_service

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

    def next_version(self, tenant_id: str, convention_id: str) -> int:
        versions = [
            document.version
            for document in self._load_all_documents(tenant_id)
            if document.convention_id == convention_id
        ]
        if not versions:
            return 1
        return max(versions) + 1

    def write_promoted_document(
        self,
        *,
        tenant_id: str,
        document: CanonicalConventionDocument,
        promoted_by: str,
        related_action_id: str,
    ) -> Path:
        tenant_dir = self.knowledge_dir / "canonical" / tenant_id
        tenant_dir.mkdir(parents=True, exist_ok=True)
        path = tenant_dir / f"{document.convention_id}.v{document.version}.canonical.json"
        temp_path = path.with_suffix(path.suffix + ".tmp")
        temp_path.write_text(
            json.dumps(
                document.model_dump(mode="json", exclude_none=True),
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        temp_path.replace(path)

        if self.audit_log_service is not None:
            self.audit_log_service.append_entry(
                tenant_id,
                AuditLogEntry(
                    event_id=f"{document.convention_id}-v{document.version}-promoted",
                    event_type="canonical_convention_promoted",
                    tenant_id=tenant_id,
                    thread_id="canonical-conventions",
                    occurred_at=datetime.now(timezone.utc),
                    summary=(
                        f"canonical_convention_promoted:{document.convention_id}:"
                        f"v{document.version}:{promoted_by}"
                    ),
                    related_action_id=related_action_id,
                ),
            )
        return path

    def _load_approved_documents(self, tenant_id: str) -> list[CanonicalConventionDocument]:
        return [
            document
            for document in self._load_all_documents(tenant_id)
            if document.status is CanonicalConventionStatus.APPROVED
        ]

    def _load_all_documents(self, tenant_id: str) -> list[CanonicalConventionDocument]:
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
            documents.append(document)
        documents.sort(key=lambda item: (item.version, item.convention_id))
        return documents

    def _dedupe_tags(self, tags: list[str]) -> list[str]:
        unique_tags: list[str] = []
        for tag in tags:
            normalized = tag.strip()
            if normalized and normalized not in unique_tags:
                unique_tags.append(normalized)
        return unique_tags[:8]
