import json
from datetime import datetime, timezone
from pathlib import Path
import shutil

from app.models.contracts import (
    AnalysisRequest,
    CanonicalPolicyScope,
    ThreadMessage,
    TriggerCommand,
)
from app.services.kernel.canonical_convention_service import CanonicalConventionService
from app.services.knowledge_base import KnowledgeBase


def build_analysis_request(*messages: str) -> AnalysisRequest:
    thread_messages = [
        ThreadMessage(
            message_id=f"om_{index}",
            sender_name="Alice",
            sent_at=datetime.now(timezone.utc),
            text=text,
        )
        for index, text in enumerate(messages, start=1)
    ]
    return AnalysisRequest(
        trigger_command=TriggerCommand.ANALYZE_INCIDENT,
        chat_id="oc_xxx",
        thread_id="omt_xxx",
        trigger_message_id="om_trigger",
        user_id="ou_xxx",
        user_display_name="Alice",
        thread_messages=thread_messages,
    )


def test_knowledge_base_lists_markdown_and_text_documents_recursively(tmp_path: Path) -> None:
    docs_dir = tmp_path / "knowledge"
    nested_dir = docs_dir / "runbooks"
    nested_dir.mkdir(parents=True)

    (docs_dir / "payment.md").write_text("# Payment\npayment issue notes", encoding="utf-8")
    (nested_dir / "auth.txt").write_text("auth issue notes", encoding="utf-8")
    (docs_dir / "release.knowledge.json").write_text(
        '{"documents":[{"doc_id":"release-1","title":"Release","content":"payment release notes"}]}',
        encoding="utf-8",
    )
    (docs_dir / "ignore.json").write_text("{}", encoding="utf-8")

    knowledge_base = KnowledgeBase(docs_dir)

    documents = knowledge_base.list_documents()

    assert [path.name for path in documents] == ["payment.md", "release.knowledge.json", "auth.txt"]


def test_knowledge_base_retrieves_relevant_citations() -> None:
    fixtures_dir = Path(__file__).parent / "fixtures" / "knowledge"
    knowledge_base = KnowledgeBase(fixtures_dir, max_hits=2)
    request = build_analysis_request(
        "payment service 5xx spike after deploy",
        "please confirm release and inspect logs",
    )

    citations = knowledge_base.retrieve_citations(request)

    assert len(citations) >= 1
    assert any(citation.source_type == "knowledge_doc" for citation in citations)
    assert any(citation.label == "Payment Service SOP" for citation in citations)
    assert any("payment-sop.md" in citation.source_uri for citation in citations)
    assert any("5xx spike" in citation.snippet.lower() for citation in citations)


def test_knowledge_base_prefers_release_notes_for_release_queries() -> None:
    fixtures_dir = Path(__file__).parent / "fixtures" / "knowledge"
    knowledge_base = KnowledgeBase(fixtures_dir, max_hits=2)
    request = build_analysis_request(
        "payment service 5xx spike after deploy",
        "please confirm release, rollback status, and inspect logs",
    )

    citations = knowledge_base.retrieve_citations(request)

    assert citations
    assert citations[0].label == "Payment Release 2026-04-10"


def test_knowledge_base_prefers_auth_runbook_for_auth_queries() -> None:
    fixtures_dir = Path(__file__).parent / "fixtures" / "knowledge"
    knowledge_base = KnowledgeBase(fixtures_dir, max_hits=2)
    request = build_analysis_request(
        "login failures are rising after token refresh",
        "please confirm auth status and token expiry handling",
    )

    citations = knowledge_base.retrieve_citations(request)

    assert citations
    assert citations[0].label == "Auth Runbook"


def test_knowledge_base_uses_second_pass_for_release_note_recall() -> None:
    fixtures_dir = Path(__file__).parent / "fixtures" / "knowledge"
    knowledge_base = KnowledgeBase(fixtures_dir, max_hits=2)
    request = build_analysis_request(
        "payment 发布后异常",
        "请确认这次发布相关变更",
    )

    citations = knowledge_base.retrieve_citations(request)

    assert citations
    assert citations[0].label == "Payment Release 2026-04-10"


def test_knowledge_base_returns_empty_when_directory_is_missing(tmp_path: Path) -> None:
    knowledge_base = KnowledgeBase(tmp_path / "missing")
    request = build_analysis_request("payment service is failing")

    assert knowledge_base.list_documents() == []
    assert knowledge_base.list_metadata() == []
    assert knowledge_base.retrieve_citations(request) == []


def test_knowledge_base_loads_structured_bundle_documents_and_retrieves_them() -> None:
    fixtures_dir = Path(__file__).parent / "fixtures" / "knowledge"
    knowledge_base = KnowledgeBase(fixtures_dir, max_hits=3)
    request = build_analysis_request(
        "please confirm the payment release and rollback notes",
        "the thread suggests the deployment touched retry middleware",
    )

    metadata = knowledge_base.list_metadata()
    citations = knowledge_base.retrieve_citations(request)

    assert any(item.doc_id == "payment-release-2026-04-10" for item in metadata)
    assert any(citation.label == "Payment Release 2026-04-10" for citation in citations)
    assert any("payment-2026-04-10" in citation.source_uri for citation in citations)
    assert any("retry middleware" in citation.snippet.lower() for citation in citations)


def test_knowledge_base_skips_unreadable_files(monkeypatch, tmp_path: Path) -> None:
    docs_dir = tmp_path / "knowledge"
    docs_dir.mkdir()
    readable = docs_dir / "payment.md"
    broken = docs_dir / "broken.md"

    readable.write_text("# Payment\npayment deployment rollback guide", encoding="utf-8")
    broken.write_text("broken content", encoding="utf-8")

    original_read_text = Path.read_text

    def fake_read_text(self: Path, *args, **kwargs) -> str:
        if self == broken:
            raise OSError("cannot read")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fake_read_text)

    knowledge_base = KnowledgeBase(docs_dir)
    metadata = knowledge_base.list_metadata()

    assert len(metadata) == 1
    assert metadata[0].doc_id == "payment"


def test_knowledge_base_filters_weak_evidence_hits(tmp_path: Path) -> None:
    docs_dir = tmp_path / "knowledge"
    docs_dir.mkdir()
    (docs_dir / "payment.md").write_text(
        "# Payment Notes\npayment issue notes",
        encoding="utf-8",
    )
    knowledge_base = KnowledgeBase(docs_dir)
    request = build_analysis_request("payment looks odd", "please help")

    citations = knowledge_base.retrieve_citations(request)

    assert citations == []


def test_knowledge_base_includes_tenant_canonical_policy_documents_in_scoped_metadata(
    tmp_path: Path,
) -> None:
    fixtures_dir = Path(__file__).parent / "fixtures" / "knowledge"
    knowledge_dir = tmp_path / "knowledge"
    shutil.copytree(fixtures_dir, knowledge_dir)
    tenant_dir = knowledge_dir / "canonical" / "oc_xxx"
    tenant_dir.mkdir(parents=True, exist_ok=True)
    (tenant_dir / "team-defaults.canonical.json").write_text(
        json.dumps(
            {
                "convention_id": "team-defaults",
                "title": "Team Defaults",
                "status": "approved",
                "policy_documents": [
                    {
                        "doc_id": "incident-approved-policy",
                        "title": "Approved Incident Policy",
                        "content": "Use the approved tenant incident policy before generic docs.",
                        "scope": "incident",
                        "tags": ["policy", "incident"],
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    knowledge_base = KnowledgeBase(
        knowledge_dir,
        canonical_convention_service=CanonicalConventionService(knowledge_dir),
    )

    tenant_metadata = knowledge_base.list_metadata(
        tenant_id="oc_xxx",
        use_case=CanonicalPolicyScope.INCIDENT,
    )
    other_tenant_metadata = knowledge_base.list_metadata(
        tenant_id="oc_other",
        use_case=CanonicalPolicyScope.INCIDENT,
    )

    assert any(item.doc_id == "incident-approved-policy" for item in tenant_metadata)
    assert not any(item.doc_id == "incident-approved-policy" for item in other_tenant_metadata)
