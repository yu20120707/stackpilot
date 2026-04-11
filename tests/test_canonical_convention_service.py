import json
from pathlib import Path

from app.models.contracts import CanonicalPolicyScope
from app.services.kernel.canonical_convention_service import CanonicalConventionService


def write_canonical_document(
    knowledge_dir: Path,
    tenant_id: str,
    payload: dict[str, object],
    *,
    filename: str,
) -> None:
    tenant_dir = knowledge_dir / "canonical" / tenant_id
    tenant_dir.mkdir(parents=True, exist_ok=True)
    (tenant_dir / filename).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def test_canonical_convention_service_loads_approved_runtime_defaults_and_scoped_policy_docs(
    tmp_path: Path,
) -> None:
    knowledge_dir = tmp_path / "knowledge"
    write_canonical_document(
        knowledge_dir,
        "oc_xxx",
        {
            "convention_id": "team-defaults",
            "title": "Team Defaults",
            "status": "approved",
            "review_defaults": {
                "default_focus_areas": ["security"],
            },
            "postmortem_style": {
                "title_prefix": "[SEV-2]",
            },
            "policy_documents": [
                {
                    "doc_id": "review-policy",
                    "title": "Canonical Review Policy",
                    "content": "Prefer security review for service-facing auth or input handling changes.",
                    "scope": "review",
                    "tags": ["policy", "review", "security"],
                },
                {
                    "doc_id": "incident-policy",
                    "title": "Canonical Incident Policy",
                    "content": "Prefer approved postmortem structure for incident write-backs.",
                    "scope": "incident",
                    "tags": ["policy", "incident"],
                },
            ],
        },
        filename="team-defaults.canonical.json",
    )
    write_canonical_document(
        knowledge_dir,
        "oc_xxx",
        {
            "convention_id": "draft-defaults",
            "title": "Draft Defaults",
            "status": "draft",
            "review_defaults": {
                "default_focus_areas": ["bug_risk"],
            },
        },
        filename="draft-defaults.canonical.json",
    )

    service = CanonicalConventionService(knowledge_dir)

    review_defaults = service.load_review_defaults("oc_xxx")
    postmortem_style = service.load_postmortem_style("oc_xxx")
    review_policy_documents = service.load_policy_documents(
        "oc_xxx",
        use_case=CanonicalPolicyScope.REVIEW,
    )
    incident_policy_documents = service.load_policy_documents(
        "oc_xxx",
        use_case=CanonicalPolicyScope.INCIDENT,
    )

    assert review_defaults is not None
    assert [item.value for item in review_defaults.default_focus_areas] == ["security"]
    assert postmortem_style is not None
    assert postmortem_style.title_prefix == "[SEV-2]"
    assert [item.metadata.doc_id for item in review_policy_documents] == ["review-policy"]
    assert [item.metadata.doc_id for item in incident_policy_documents] == ["incident-policy"]
    assert "canonical" in review_policy_documents[0].metadata.tags
