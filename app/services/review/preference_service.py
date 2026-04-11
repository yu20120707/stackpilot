from __future__ import annotations

import re

from app.models.contracts import MemoryScope, ReviewFeedbackStatus, ReviewFinding, ReviewFocusArea
from app.services.kernel.org_convention_service import OrgConventionService
from app.services.kernel.memory_service import MemoryService


FOCUS_KEYWORDS: dict[ReviewFocusArea, tuple[str, ...]] = {
    ReviewFocusArea.BUG_RISK: ("bug", "风险", "回归", "异常", "逻辑", "bugrisk"),
    ReviewFocusArea.TEST_GAP: ("test", "测试", "case", "coverage", "单测", "集成测试"),
    ReviewFocusArea.SECURITY: ("security", "安全", "鉴权", "权限", "注入", "xss", "csrf", "sql"),
}
FENCED_BLOCK_PATTERN = re.compile(r"```.*?```", re.DOTALL)
URL_PATTERN = re.compile(r"https?://\S+", re.IGNORECASE)


class ReviewPreferenceService:
    def __init__(
        self,
        memory_service: MemoryService,
        *,
        org_convention_service: OrgConventionService | None = None,
    ) -> None:
        self.memory_service = memory_service
        self.org_convention_service = org_convention_service

    def resolve_focus_areas(
        self,
        *,
        scope: MemoryScope,
        message_text: str,
    ) -> tuple[list[ReviewFocusArea], list[ReviewFocusArea]]:
        explicit_focus_areas = self.extract_focus_areas(message_text)
        if explicit_focus_areas:
            return explicit_focus_areas, explicit_focus_areas

        user_memory = self.memory_service.load_user_memory(scope)
        user_preferences = self._extract_preferred_focus_areas(user_memory)
        if user_preferences:
            return user_preferences, []

        org_preferences = self._load_org_default_focus_areas(scope.tenant_id)
        if org_preferences:
            return org_preferences, []

        return [ReviewFocusArea.BUG_RISK, ReviewFocusArea.TEST_GAP], []

    def observe_review_request(
        self,
        *,
        scope: MemoryScope,
        explicit_focus_areas: list[ReviewFocusArea],
    ) -> None:
        if not explicit_focus_areas:
            return

        user_memory = self.memory_service.load_user_memory(scope)
        review_preferences = self._load_review_preferences_mapping(user_memory)
        focus_set_key = self._focus_set_key(explicit_focus_areas)
        request_counts = {
            key: int(value)
            for key, value in review_preferences.get("focus_request_counts", {}).items()
            if isinstance(value, int)
        }
        request_counts[focus_set_key] = request_counts.get(focus_set_key, 0) + 1
        review_preferences["focus_request_counts"] = request_counts
        review_preferences["last_requested_focus_areas"] = [item.value for item in explicit_focus_areas]
        if request_counts[focus_set_key] >= 2:
            review_preferences["preferred_focus_areas"] = [item.value for item in explicit_focus_areas]
        user_memory["review_preferences"] = review_preferences
        self.memory_service.save_user_memory(scope, user_memory)

    def observe_feedback(
        self,
        *,
        scope: MemoryScope,
        finding: ReviewFinding,
        feedback_status: ReviewFeedbackStatus,
    ) -> None:
        if feedback_status is not ReviewFeedbackStatus.ACCEPTED or not finding.focus_areas:
            return

        user_memory = self.memory_service.load_user_memory(scope)
        review_preferences = self._load_review_preferences_mapping(user_memory)
        accepted_counts = {
            key: int(value)
            for key, value in review_preferences.get("accepted_focus_counts", {}).items()
            if isinstance(value, int)
        }
        for focus_area in finding.focus_areas:
            accepted_counts[focus_area.value] = accepted_counts.get(focus_area.value, 0) + 1
        review_preferences["accepted_focus_counts"] = accepted_counts

        top_focuses = [
            ReviewFocusArea(key)
            for key, count in sorted(
                accepted_counts.items(),
                key=lambda item: item[1],
                reverse=True,
            )[:2]
            if count >= 2
        ]
        if top_focuses:
            review_preferences["preferred_focus_areas"] = [item.value for item in top_focuses]

        user_memory["review_preferences"] = review_preferences
        self.memory_service.save_user_memory(scope, user_memory)

    def extract_focus_areas(self, message_text: str) -> list[ReviewFocusArea]:
        normalized_text = URL_PATTERN.sub(" ", FENCED_BLOCK_PATTERN.sub(" ", message_text.lower()))
        normalized_text = re.sub(r"\s+", "", normalized_text)
        focus_areas: list[ReviewFocusArea] = []
        for focus_area, keywords in FOCUS_KEYWORDS.items():
            if any(keyword.lower() in normalized_text for keyword in keywords):
                focus_areas.append(focus_area)
        return focus_areas

    def _extract_preferred_focus_areas(self, memory_payload: dict[str, object]) -> list[ReviewFocusArea]:
        review_preferences = memory_payload.get("review_preferences")
        if not isinstance(review_preferences, dict):
            return []

        raw_focus_areas = review_preferences.get("preferred_focus_areas")
        if not isinstance(raw_focus_areas, list):
            return []

        focus_areas: list[ReviewFocusArea] = []
        for item in raw_focus_areas:
            if not isinstance(item, str):
                continue
            try:
                focus_areas.append(ReviewFocusArea(item))
            except ValueError:
                continue
        return focus_areas

    def _load_review_preferences_mapping(self, memory_payload: dict[str, object]) -> dict[str, object]:
        review_preferences = memory_payload.get("review_preferences")
        if isinstance(review_preferences, dict):
            return dict(review_preferences)
        return {}

    def _load_org_default_focus_areas(self, tenant_id: str) -> list[ReviewFocusArea]:
        if self.org_convention_service is not None:
            defaults = self.org_convention_service.load_review_defaults(tenant_id)
            if defaults is not None and defaults.default_focus_areas:
                return defaults.default_focus_areas

        org_memory = self.memory_service.load_org_memory_for_tenant(tenant_id)
        return self._extract_preferred_focus_areas(org_memory)

    def _focus_set_key(self, focus_areas: list[ReviewFocusArea]) -> str:
        return "|".join(sorted(item.value for item in focus_areas))
