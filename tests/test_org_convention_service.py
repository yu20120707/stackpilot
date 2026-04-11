from pathlib import Path

from app.services.kernel.memory_service import MemoryService
from app.services.kernel.org_convention_service import OrgConventionService


def test_org_convention_service_loads_review_defaults_and_postmortem_style(tmp_path: Path) -> None:
    memory_service = MemoryService(tmp_path / "memory")
    memory_service.save_org_memory_for_tenant(
        "oc_xxx",
        {
            "review_defaults": {
                "default_focus_areas": ["security"],
            },
            "postmortem_style": {
                "template_name": "enterprise-standard",
                "title_prefix": "[SEV-2]",
                "follow_up_prefix": "团队跟进：",
                "section_labels": {
                    "incident_summary": "背景摘要：",
                    "follow_up_actions": "团队后续动作：",
                },
            },
        },
    )
    service = OrgConventionService(memory_service)

    review_defaults = service.load_review_defaults("oc_xxx")
    postmortem_style = service.load_postmortem_style("oc_xxx")

    assert review_defaults is not None
    assert [item.value for item in review_defaults.default_focus_areas] == ["security"]
    assert postmortem_style is not None
    assert postmortem_style.title_prefix == "[SEV-2]"
    assert postmortem_style.section_labels["incident_summary"] == "背景摘要："
