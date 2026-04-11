import json
from pathlib import Path
import re

from app.core.logging import get_logger
from app.models.contracts import (
    AnalysisRequest,
    KnowledgeCitation,
    KnowledgeDocumentMetadata,
)
from app.services.retrieval.models import LoadedKnowledgeDocument
from app.services.retrieval.service import RetrievalService


logger = get_logger(__name__)
DOCUMENT_EXTENSIONS = {".md", ".txt"}
STRUCTURED_BUNDLE_SUFFIX = ".knowledge.json"
MARKDOWN_HEADING_PATTERN = re.compile(r"^\s*#\s+(.+?)\s*$", re.MULTILINE)


class KnowledgeBase:
    def __init__(self, knowledge_dir: Path, max_hits: int = 5) -> None:
        self.knowledge_dir = knowledge_dir
        self.max_hits = max_hits
        self.retrieval_service = RetrievalService(
            document_loader=self.load_documents,
            default_max_hits=max_hits,
        )

    def list_documents(self) -> list[Path]:
        if not self.knowledge_dir.exists():
            return []

        return sorted(
            path
            for path in self.knowledge_dir.rglob("*")
            if path.is_file() and self._is_supported_document(path)
        )

    def load_documents(self) -> list[LoadedKnowledgeDocument]:
        documents: list[LoadedKnowledgeDocument] = []

        for path in self.list_documents():
            try:
                if self._is_structured_bundle(path):
                    documents.extend(self._load_structured_bundle(path))
                    continue

                content = path.read_text(encoding="utf-8").strip()
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                logger.warning("Skipping unsupported or unreadable knowledge file: %s", path)
                continue

            if not content:
                continue

            documents.append(
                LoadedKnowledgeDocument(
                    metadata=self._build_metadata(path=path, content=content),
                    content=content,
                )
            )

        return documents

    def list_metadata(self) -> list[KnowledgeDocumentMetadata]:
        return [document.metadata for document in self.load_documents()]

    def retrieve_citations(
        self,
        analysis_request: AnalysisRequest,
        *,
        max_hits: int | None = None,
    ) -> list[KnowledgeCitation]:
        return self.retrieval_service.retrieve(
            analysis_request,
            max_hits=max_hits,
        )

    def _is_supported_document(self, path: Path) -> bool:
        return path.suffix.lower() in DOCUMENT_EXTENSIONS or self._is_structured_bundle(path)

    def _is_structured_bundle(self, path: Path) -> bool:
        return path.name.lower().endswith(STRUCTURED_BUNDLE_SUFFIX)

    def _build_metadata(self, *, path: Path, content: str) -> KnowledgeDocumentMetadata:
        title_match = MARKDOWN_HEADING_PATTERN.search(content)
        title = title_match.group(1).strip() if title_match else self._humanize_stem(path.stem)

        return KnowledgeDocumentMetadata(
            doc_id=path.stem,
            title=title,
            path=self._format_source_path(path),
            tags=self._derive_tags(path),
        )

    def _load_structured_bundle(self, path: Path) -> list[LoadedKnowledgeDocument]:
        payload = json.loads(path.read_text(encoding="utf-8"))
        bundle_source_name: str | None = None

        if isinstance(payload, dict):
            raw_documents = payload.get("documents")
            bundle_source_name = self._normalize_optional_text(payload.get("source_name"))
        else:
            raw_documents = payload

        if not isinstance(raw_documents, list):
            raise ValueError("Structured knowledge bundle must contain a document list.")

        documents: list[LoadedKnowledgeDocument] = []
        for index, raw_document in enumerate(raw_documents, start=1):
            if not isinstance(raw_document, dict):
                continue

            content = self._normalize_optional_text(raw_document.get("content"))
            if not content:
                continue

            doc_id = self._normalize_optional_text(raw_document.get("doc_id")) or f"{path.stem}-{index}"
            title = (
                self._normalize_optional_text(raw_document.get("title"))
                or self._humanize_stem(doc_id)
            )
            source_uri = (
                self._normalize_optional_text(raw_document.get("source_uri"))
                or self._format_source_path(path)
            )
            tags = self._normalize_tags(raw_document.get("tags"))
            if bundle_source_name:
                tags = [bundle_source_name, *tags]

            documents.append(
                LoadedKnowledgeDocument(
                    metadata=KnowledgeDocumentMetadata(
                        doc_id=doc_id,
                        title=title,
                        path=source_uri,
                        tags=tags[:5],
                    ),
                    content=content,
                )
            )

        return documents

    def _format_source_path(self, path: Path) -> str:
        try:
            return path.relative_to(Path.cwd()).as_posix()
        except ValueError:
            return path.as_posix()

    def _derive_tags(self, path: Path) -> list[str]:
        parts = [segment for segment in path.stem.replace("_", "-").split("-") if segment]
        return parts[:5]

    def _normalize_optional_text(self, value: object) -> str | None:
        if not isinstance(value, str):
            return None
        normalized = value.strip()
        return normalized or None

    def _normalize_tags(self, value: object) -> list[str]:
        if not isinstance(value, list):
            return []

        tags: list[str] = []
        for item in value:
            if not isinstance(item, str):
                continue
            normalized = item.strip()
            if normalized and normalized not in tags:
                tags.append(normalized)
        return tags

    def _humanize_stem(self, stem: str) -> str:
        return stem.replace("-", " ").replace("_", " ").strip().title()
