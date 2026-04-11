import json
from pathlib import Path

from app.services.kernel.memory_service import MemoryService
from app.services.kernel.canonical_convention_service import CanonicalConventionService
from app.services.kernel.org_convention_service import OrgConventionService


def test_org_convention_service_prefers_canonical_defaults_and_merges_postmortem_style(
    tmp_path: Path,
) -> None:
    memory_service = MemoryService(tmp_path / "memory")
    memory_service.save_org_memory_for_tenant(
        "oc_xxx",
        {
            "review_defaults": {
                "default_focus_areas": ["bug_risk"],
            },
            "postmortem_style": {
                "follow_up_prefix": "团队跟进：",
                "section_labels": {
                    "incident_summary": "背景摘要：",
                },
            },
        },
    )
    knowledge_dir = tmp_path / "knowledge"
    tenant_dir = knowledge_dir / "canonical" / "oc_xxx"
    tenant_dir.mkdir(parents=True, exist_ok=True)
    (tenant_dir / "team-defaults.canonical.json").write_text(
        json.dumps(
            {
                "convention_id": "team-defaults",
                "title": "Team Defaults",
                "status": "approved",
                "review_defaults": {
                    "default_focus_areas": ["security"],
                },
                "postmortem_style": {
                    "title_prefix": "[SEV-2]",
                    "section_labels": {
                        "follow_up_actions": "团队后续动作：",
                    },
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    service = OrgConventionService(
        memory_service,
        canonical_convention_service=CanonicalConventionService(knowledge_dir),
    )

    review_defaults = service.load_review_defaults("oc_xxx")
    postmortem_style = service.load_postmortem_style("oc_xxx")

    assert review_defaults is not None
    assert [item.value for item in review_defaults.default_focus_areas] == ["security"]
    assert postmortem_style is not None
    assert postmortem_style.title_prefix == "[SEV-2]"
    assert postmortem_style.section_labels["incident_summary"] == "背景摘要："
    assert postmortem_style.section_labels["follow_up_actions"] == "团队后续动作："
    assert postmortem_style.follow_up_prefix == "团队跟进："
