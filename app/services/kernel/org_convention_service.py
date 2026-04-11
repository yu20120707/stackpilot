from __future__ import annotations

from pydantic import ValidationError

from app.models.contracts import OrgPostmortemStyle, OrgReviewDefaults
from app.services.kernel.memory_service import MemoryService


class OrgConventionService:
    def __init__(self, memory_service: MemoryService) -> None:
        self.memory_service = memory_service

    def load_review_defaults(self, tenant_id: str) -> OrgReviewDefaults | None:
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

    def load_postmortem_style(self, tenant_id: str) -> OrgPostmortemStyle | None:
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
