from dataclasses import dataclass
import json
from pathlib import Path
import re

from app.core.logging import get_logger
from app.models.contracts import (
    AnalysisRequest,
    KnowledgeCitation,
    KnowledgeDocumentMetadata,
    SourceType,
)


logger = get_logger(__name__)
DOCUMENT_EXTENSIONS = {".md", ".txt"}
STRUCTURED_BUNDLE_SUFFIX = ".knowledge.json"
ASCII_TOKEN_PATTERN = re.compile(r"[a-z0-9_./-]{2,}")
CJK_SEGMENT_PATTERN = re.compile(r"[\u4e00-\u9fff]{2,}")
WHITESPACE_PATTERN = re.compile(r"\s+")
MARKDOWN_HEADING_PATTERN = re.compile(r"^\s*#\s+(.+?)\s*$", re.MULTILINE)
STOP_WORDS = {
    "the",
    "and",
    "for",
    "with",
    "this",
    "that",
    "from",
    "into",
    "after",
    "before",
    "then",
    "when",
    "http",
    "https",
    "service",
}


@dataclass(slots=True)
class LoadedKnowledgeDocument:
    metadata: KnowledgeDocumentMetadata
    content: str


class KnowledgeBase:
    def __init__(self, knowledge_dir: Path, max_hits: int = 5) -> None:
        self.knowledge_dir = knowledge_dir
        self.max_hits = max_hits

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
        query_text = "\n".join(message.text for message in analysis_request.thread_messages)
        query_terms = self._extract_terms(query_text)
        if not query_terms:
            return []

        scored_documents: list[tuple[int, str, LoadedKnowledgeDocument]] = []
        for document in self.load_documents():
            score, best_term = self._score_document(document.content, query_terms)
            if score <= 0:
                continue
            scored_documents.append((score, best_term, document))

        scored_documents.sort(
            key=lambda item: (-item[0], item[2].metadata.title.lower(), item[2].metadata.path)
        )

        limit = max_hits or self.max_hits
        citations: list[KnowledgeCitation] = []
        for score, best_term, document in scored_documents[:limit]:
            _ = score
            citations.append(
                KnowledgeCitation(
                    source_type=SourceType.KNOWLEDGE_DOC,
                    label=document.metadata.title,
                    source_uri=document.metadata.path,
                    snippet=self._build_snippet(document.content, best_term),
                )
            )

        return citations

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

    def _extract_terms(self, text: str) -> set[str]:
        normalized = text.lower()
        terms = {
            token
            for token in ASCII_TOKEN_PATTERN.findall(normalized)
            if token not in STOP_WORDS
        }

        for segment in CJK_SEGMENT_PATTERN.findall(normalized):
            terms.add(segment)
            if len(segment) > 2:
                for index in range(len(segment) - 1):
                    terms.add(segment[index : index + 2])

        return {term for term in terms if term.strip()}

    def _score_document(self, content: str, query_terms: set[str]) -> tuple[int, str]:
        normalized_content = content.lower()
        matched_terms = [term for term in query_terms if term in normalized_content]
        if not matched_terms:
            return 0, ""

        score = sum(min(len(term), 8) for term in matched_terms)
        best_term = min(
            matched_terms,
            key=lambda term: (normalized_content.find(term), -len(term)),
        )
        return score, best_term

    def _build_snippet(self, content: str, best_term: str) -> str:
        squashed = WHITESPACE_PATTERN.sub(" ", content).strip()
        if not squashed:
            return ""

        if not best_term:
            return squashed[:160]

        normalized_squashed = squashed.lower()
        index = normalized_squashed.find(best_term.lower())
        if index < 0:
            return squashed[:160]

        start = max(0, index - 40)
        end = min(len(squashed), index + len(best_term) + 80)
        snippet = squashed[start:end].strip()

        if start > 0:
            snippet = f"...{snippet}"
        if end < len(squashed):
            snippet = f"{snippet}..."

        return snippet
