from __future__ import annotations

from pydantic import ValidationError

from app.models.contracts import OrgPostmortemStyle, OrgReviewDefaults
from app.services.kernel.canonical_convention_service import CanonicalConventionService
from app.services.kernel.memory_service import MemoryService


class OrgConventionService:
    def __init__(
        self,
        memory_service: MemoryService,
        *,
        canonical_convention_service: CanonicalConventionService | None = None,
    ) -> None:
        self.memory_service = memory_service
        self.canonical_convention_service = canonical_convention_service

    def load_review_defaults(self, tenant_id: str) -> OrgReviewDefaults | None:
        if self.canonical_convention_service is not None:
            canonical_defaults = self.canonical_convention_service.load_review_defaults(tenant_id)
            if canonical_defaults is not None and canonical_defaults.default_focus_areas:
                return canonical_defaults

        return self._load_review_defaults_from_org_memory(tenant_id)

    def load_postmortem_style(self, tenant_id: str) -> OrgPostmortemStyle | None:
        payload: dict[str, object] = {}
        section_labels: dict[str, str] = {}

        org_style = self._load_postmortem_style_from_org_memory(tenant_id)
        if org_style is not None:
            payload.update(
                {
                    "template_name": org_style.template_name,
                    "title_prefix": org_style.title_prefix,
                    "follow_up_prefix": org_style.follow_up_prefix,
                }
            )
            section_labels.update(org_style.section_labels)

        if self.canonical_convention_service is not None:
            canonical_style = self.canonical_convention_service.load_postmortem_style(tenant_id)
            if canonical_style is not None:
                if canonical_style.template_name:
                    payload["template_name"] = canonical_style.template_name
                if canonical_style.title_prefix:
                    payload["title_prefix"] = canonical_style.title_prefix
                if canonical_style.follow_up_prefix:
                    payload["follow_up_prefix"] = canonical_style.follow_up_prefix
                if canonical_style.section_labels:
                    section_labels.update(canonical_style.section_labels)

        if section_labels:
            payload["section_labels"] = section_labels
        payload = {key: value for key, value in payload.items() if value}
        if not payload:
            return None

        return OrgPostmortemStyle.model_validate(payload)

    def _load_review_defaults_from_org_memory(self, tenant_id: str) -> OrgReviewDefaults | None:
        payload = self.memory_service.load_org_memory_for_tenant(tenant_id)
        if not payload:
            return None

        candidate_payloads = []
        review_defaults = payload.get("review_defaults")
        if isinstance(review_defaults, dict):
            candidate_payloads.append(review_defaults)

        review_preferences = payload.get("review_preferences")
        if isinstance(review_preferences, dict):
            preferred_focus_areas = review_preferences.get("preferred_focus_areas")
            if isinstance(preferred_focus_areas, list):
                candidate_payloads.append({"default_focus_areas": preferred_focus_areas})

        for candidate_payload in candidate_payloads:
            try:
                defaults = OrgReviewDefaults.model_validate(candidate_payload)
            except ValidationError:
                continue
            if defaults.default_focus_areas:
                return defaults

        return None

    def _load_postmortem_style_from_org_memory(self, tenant_id: str) -> OrgPostmortemStyle | None:
        payload = self.memory_service.load_org_memory_for_tenant(tenant_id)
        if not payload:
            return None

        postmortem_style = payload.get("postmortem_style")
        if not isinstance(postmortem_style, dict):
            return None

        try:
            return OrgPostmortemStyle.model_validate(postmortem_style)
        except ValidationError:
            return None
