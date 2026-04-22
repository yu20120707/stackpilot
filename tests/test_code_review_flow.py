import json
from datetime import datetime
from pathlib import Path
import shutil

import pytest

from app.clients.github_review_client import GitHubIssueComment
from app.clients.feishu_client import FeishuClient
from app.models.contracts import (
    ActionScope,
    CodeReviewRequest,
    DiffFileChange,
    DiffHunk,
    FeishuReplySendResult,
    InteractionEventType,
    NormalizedFeishuMessageEvent,
    ReviewFeedbackStatus,
    ReviewFocusArea,
    ReviewOutcomeSource,
    ReviewOutcomeStatus,
    ReviewSourceType,
    TriggerCommand,
)
from app.services.kernel.audit_log_service import AuditLogService
from app.services.kernel.action_queue_service import ActionQueueService
from app.services.kernel.canonical_convention_service import CanonicalConventionService
from app.services.kernel.interaction_recorder import InteractionRecorder
from app.services.kernel.memory_service import MemoryService
from app.services.kernel.org_convention_service import OrgConventionService
from app.services.knowledge_base import KnowledgeBase
from app.services.review.diff_reader import DiffReader
from app.services.review.flow import CodeReviewFlow
from app.services.review.outcome_service import ReviewOutcomeService
from app.services.review.preference_service import ReviewPreferenceService
from app.services.review.policy_service import ReviewPolicyService
from app.services.review.publish_service import ReviewPublishService
from app.services.review.renderer import ReviewRenderer
from app.services.review.service import ReviewService
from app.services.growth.skill_miner import SkillMiner
from app.services.growth.skill_registry import SkillRegistry


FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_text(*relative_parts: str) -> str:
    return FIXTURES_DIR.joinpath(*relative_parts).read_text(encoding="utf-8")


class FakeReviewFeishuClient(FeishuClient):
    def __init__(self, *, reply_success: bool = True) -> None:
        super().__init__()
        self.reply_success = reply_success
        self.reply_calls: list[tuple[str, str, str, str]] = []

    async def reply_to_thread(
        self,
        *,
        chat_id: str,
        thread_id: str,
        trigger_message_id: str,
        reply_text: str,
    ) -> FeishuReplySendResult:
        self.reply_calls.append((chat_id, thread_id, trigger_message_id, reply_text))
        if not self.reply_success:
            return FeishuReplySendResult(
                success=False,
                error_code="reply_failed",
                error_message="feishu_send_failed",
            )
        return FeishuReplySendResult(success=True, reply_message_id="om_review_reply")


class FakeLLMClient:
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[tuple[str, str]] = []

    async def generate_structured_summary(self, *, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        return self.response


class FakeGitHubReviewClient:
    def __init__(
        self,
        *,
        patch_text: str | None = None,
        publish_url: str | None = None,
        issue_comments: list[GitHubIssueComment] | None = None,
    ) -> None:
        self.patch_text = patch_text
        self.publish_url = publish_url
        self.issue_comments = issue_comments or []
        self.fetch_calls: list[str] = []
        self.publish_calls: list[tuple[str, str]] = []
        self.list_comment_calls: list[str] = []

    async def fetch_pull_request_diff(self, pull_request_url: str) -> str | None:
        self.fetch_calls.append(pull_request_url)
        return self.patch_text

    async def publish_issue_comment(self, *, pull_request_url: str, body: str) -> GitHubIssueComment | None:
        self.publish_calls.append((pull_request_url, body))
        if self.publish_url is None:
            return None
        return GitHubIssueComment(
            comment_id=101,
            html_url=self.publish_url,
            body=body,
            author_login="stackpilot-bot",
            created_at=datetime.fromisoformat("2026-04-11T02:05:00+00:00"),
        )

    async def list_issue_comments(self, *, pull_request_url: str) -> list[GitHubIssueComment]:
        self.list_comment_calls.append(pull_request_url)
        return list(self.issue_comments)


def build_growth_services(tmp_path: Path) -> tuple[InteractionRecorder, SkillMiner]:
    audit_log_service = AuditLogService(tmp_path / "records")
    interaction_recorder = InteractionRecorder(
        tmp_path / "records",
        audit_log_service=audit_log_service,
    )
    skill_registry = SkillRegistry(
        tmp_path / "skills",
        audit_log_service=audit_log_service,
    )
    skill_miner = SkillMiner(
        interaction_recorder=interaction_recorder,
        skill_registry=skill_registry,
    )
    return interaction_recorder, skill_miner


def build_trigger_event(message_text: str) -> NormalizedFeishuMessageEvent:
    return NormalizedFeishuMessageEvent(
        chat_id="oc_xxx",
        message_id="om_review_1",
        thread_id="omt_review",
        sender_id="ou_xxx",
        sender_name="Alice",
        message_text=message_text,
        mentions_bot=True,
        event_time=datetime.fromisoformat("2026-04-11T10:00:00+08:00"),
    )


def build_review_flow(
    *,
    tmp_path: Path,
    llm_response: str,
    github_patch: str | None = None,
    publish_url: str | None = None,
    issue_comments: list[GitHubIssueComment] | None = None,
    reply_success: bool = True,
    knowledge_dir: Path | None = None,
) -> tuple[CodeReviewFlow, FakeReviewFeishuClient, FakeGitHubReviewClient, ActionQueueService, InteractionRecorder, MemoryService]:
    feishu_client = FakeReviewFeishuClient(reply_success=reply_success)
    llm_client = FakeLLMClient(llm_response)
    github_client = FakeGitHubReviewClient(
        patch_text=github_patch,
        publish_url=publish_url,
        issue_comments=issue_comments,
    )
    interaction_recorder, skill_miner = build_growth_services(tmp_path)
    action_queue_service = ActionQueueService(tmp_path / "actions")
    memory_service = MemoryService(tmp_path / "memory")
    knowledge_root = knowledge_dir or FIXTURES_DIR / "knowledge"
    canonical_convention_service = CanonicalConventionService(knowledge_root)
    review_renderer = ReviewRenderer()
    review_flow = CodeReviewFlow(
        feishu_client=feishu_client,
        github_review_client=github_client,
        diff_reader=DiffReader(),
        review_policy_service=ReviewPolicyService(
            KnowledgeBase(
                knowledge_root,
                max_hits=3,
                canonical_convention_service=canonical_convention_service,
            )
        ),
        review_preference_service=ReviewPreferenceService(
            memory_service,
            org_convention_service=OrgConventionService(
                memory_service,
                canonical_convention_service=canonical_convention_service,
            ),
        ),
        review_service=ReviewService(llm_client),
        review_renderer=review_renderer,
        review_publish_service=ReviewPublishService(
            action_queue_service=action_queue_service,
            github_review_client=github_client,
            review_renderer=review_renderer,
        ),
        review_outcome_service=ReviewOutcomeService(github_client),
        memory_service=memory_service,
        interaction_recorder=interaction_recorder,
        skill_miner=skill_miner,
    )
    return review_flow, feishu_client, github_client, action_queue_service, interaction_recorder, memory_service


INLINE_PATCH_MESSAGE = """@stackpilot 审一下这个 diff
```diff
diff --git a/app/services/tickets.py b/app/services/tickets.py
index 0000000..1111111 100644
--- a/app/services/tickets.py
+++ b/app/services/tickets.py
@@ -10,2 +10,4 @@ def build_ticket(payload):
-title = payload[\"title\"]
+title = payload.get(\"title\").strip()
+owner = payload.get(\"owner\", \"unknown\")
 return {\"title\": title, \"owner\": owner}
```
"""


@pytest.mark.anyio
async def test_review_service_prioritizes_risk_sensitive_files_in_prompt() -> None:
    fake_llm = FakeLLMClient(load_text("analysis", "code_review_success.json"))
    review_service = ReviewService(fake_llm)
    request = CodeReviewRequest(
        trigger_command=TriggerCommand.REVIEW_CODE,
        chat_id="oc_xxx",
        thread_id="omt_review_prompt",
        trigger_message_id="om_review_prompt_1",
        user_id="ou_xxx",
        source_type=ReviewSourceType.PATCH_TEXT,
        source_ref="inline_patch",
        raw_input="diff --git a/app/services/auth/token_service.py b/app/services/auth/token_service.py",
        normalized_patch="diff --git a/app/services/auth/token_service.py b/app/services/auth/token_service.py",
        files=[
            DiffFileChange(
                file_path="docs/notes.md",
                change_type="modified",
                additions=1,
                deletions=0,
                hunks=[DiffHunk(header="@@ -1 +1 @@ notes", snippet="+docs change")],
            ),
            DiffFileChange(
                file_path="app/services/auth/token_service.py",
                change_type="modified",
                additions=2,
                deletions=1,
                hunks=[DiffHunk(header="@@ -1 +1 @@ token", snippet="+token = value")],
            ),
            DiffFileChange(
                file_path="tests/test_token_service.py",
                change_type="modified",
                additions=4,
                deletions=0,
                hunks=[DiffHunk(header="@@ -1 +1 @@ test", snippet="+assert token")],
            ),
        ],
        focus_areas=[ReviewFocusArea.BUG_RISK, ReviewFocusArea.SECURITY],
        source_message_text="@stackpilot 审一下这个 diff",
    )

    await review_service.review(request)

    _, user_prompt = fake_llm.calls[0]
    assert "patch_overview:" in user_prompt
    assert "- changed_files: 3" in user_prompt
    assert "prioritized_files:" in user_prompt
    assert user_prompt.index("tests/test_token_service.py") < user_prompt.index("docs/notes.md")
    assert user_prompt.index("app/services/auth/token_service.py") < user_prompt.index("docs/notes.md")


@pytest.mark.anyio
async def test_review_service_backfills_evidence_from_matching_hunk() -> None:
    llm_response = json.dumps(
        {
            "status": "success",
            "overall_assessment": "owner default handling needs attention.",
            "overall_risk": "medium",
            "findings": [
                {
                    "title": "Missing owner default fallback",
                    "severity": "medium",
                    "summary": "The owner fallback hunk should be used as evidence.",
                    "file_path": "app/services/auth/token_service.py",
                    "line_start": 18,
                    "line_end": 19,
                    "evidence": [],
                }
            ],
            "missing_context": [],
            "publish_recommendation": "Keep as draft.",
        }
    )
    fake_llm = FakeLLMClient(llm_response)
    review_service = ReviewService(fake_llm)
    request = CodeReviewRequest(
        trigger_command=TriggerCommand.REVIEW_CODE,
        chat_id="oc_xxx",
        thread_id="omt_review_prompt",
        trigger_message_id="om_review_prompt_2",
        user_id="ou_xxx",
        source_type=ReviewSourceType.PATCH_TEXT,
        source_ref="inline_patch",
        raw_input="diff --git a/app/services/auth/token_service.py b/app/services/auth/token_service.py",
        normalized_patch="diff --git a/app/services/auth/token_service.py b/app/services/auth/token_service.py",
        files=[
            DiffFileChange(
                file_path="app/services/auth/token_service.py",
                change_type="modified",
                additions=2,
                deletions=1,
                hunks=[
                    DiffHunk(
                        header="@@ -1 +1 @@ token",
                        snippet="+token = payload.get(\"token\")",
                    ),
                    DiffHunk(
                        header="@@ -10 +10 @@ owner",
                        snippet="+owner = payload.get(\"owner\", \"unknown\")",
                    ),
                ],
            ),
        ],
        focus_areas=[ReviewFocusArea.BUG_RISK, ReviewFocusArea.SECURITY],
        source_message_text="@stackpilot 审一下这个 diff",
    )

    review_draft = await review_service.review(request)

    assert review_draft.findings[0].evidence
    evidence = review_draft.findings[0].evidence[0]
    assert evidence.label.endswith("@@ -10 +10 @@ owner")
    assert "owner = payload.get(\"owner\", \"unknown\")" in evidence.snippet


@pytest.mark.anyio
async def test_code_review_flow_reviews_inline_patch_and_records_draft(tmp_path: Path) -> None:
    review_flow, feishu_client, _, _, interaction_recorder, memory_service = build_review_flow(
        tmp_path=tmp_path,
        llm_response=load_text("analysis", "code_review_success.json"),
    )

    await review_flow.process_trigger(
        trigger_command=TriggerCommand.REVIEW_CODE,
        trigger_event=build_trigger_event(INLINE_PATCH_MESSAGE),
    )

    assert len(feishu_client.reply_calls) == 1
    assert "代码审查结论：" in feishu_client.reply_calls[0][3]
    assert "Missing null-safe title normalization" in feishu_client.reply_calls[0][3]

    scope = ActionScope(tenant_id="oc_xxx", thread_id="omt_review")
    records = interaction_recorder.list_thread_records(scope)
    assert [record.event_type for record in records] == [InteractionEventType.REVIEW_DRAFT_SENT]
    review_state = memory_service.load_review_state(memory_service.resolve_scope(build_trigger_event(INLINE_PATCH_MESSAGE)))
    assert review_state is not None
    assert review_state.findings[0].finding_id == "F1"


@pytest.mark.anyio
async def test_code_review_flow_fetches_github_pr_and_prepares_publish_action(tmp_path: Path) -> None:
    patch_text = load_text("analysis", "code_review_success.json")
    _ = patch_text
    review_flow, feishu_client, github_client, action_queue_service, _, _ = build_review_flow(
        tmp_path=tmp_path,
        llm_response=load_text("analysis", "code_review_success.json"),
        github_patch=INLINE_PATCH_MESSAGE.split("```diff", maxsplit=1)[1].split("```", maxsplit=1)[0].strip(),
    )

    await review_flow.process_trigger(
        trigger_command=TriggerCommand.REVIEW_CODE,
        trigger_event=build_trigger_event("@stackpilot 帮我 review 这个 PR https://github.com/openai/demo/pull/12"),
    )

    assert github_client.fetch_calls == ["https://github.com/openai/demo/pull/12"]
    assert "批准动作 R1" in feishu_client.reply_calls[0][3]
    scope = ActionScope(tenant_id="oc_xxx", thread_id="omt_review")
    pending_actions = action_queue_service.list_pending_actions(scope)
    assert [action.action_id for action in pending_actions] == ["R1"]


@pytest.mark.anyio
async def test_code_review_flow_executes_publish_approval(tmp_path: Path) -> None:
    review_flow, feishu_client, github_client, action_queue_service, interaction_recorder, memory_service = build_review_flow(
        tmp_path=tmp_path,
        llm_response=load_text("analysis", "code_review_success.json"),
        github_patch=INLINE_PATCH_MESSAGE.split("```diff", maxsplit=1)[1].split("```", maxsplit=1)[0].strip(),
        publish_url="https://github.com/openai/demo/pull/12#issuecomment-1",
    )

    await review_flow.process_trigger(
        trigger_command=TriggerCommand.REVIEW_CODE,
        trigger_event=build_trigger_event("@stackpilot 帮我 review 这个 PR https://github.com/openai/demo/pull/12"),
    )
    handled = await review_flow.process_approval(
        trigger_event=build_trigger_event("批准动作 R1").model_copy(
            update={"message_id": "om_review_approve_1"}
        ),
    )

    assert handled is True
    assert github_client.publish_calls
    assert "AI Code Review Draft" in github_client.publish_calls[0][1]
    scope = ActionScope(tenant_id="oc_xxx", thread_id="omt_review")
    persisted_action = action_queue_service.find_action(scope, "R1")
    assert persisted_action is not None
    assert persisted_action.status.value == "executed"
    assert persisted_action.review_publish_request is not None
    assert persisted_action.review_publish_request.published_ref == "https://github.com/openai/demo/pull/12#issuecomment-1"
    assert persisted_action.review_publish_request.published_comment_id == 101
    assert "https://github.com/openai/demo/pull/12#issuecomment-1" in feishu_client.reply_calls[1][3]
    review_state = memory_service.load_review_state(
        memory_service.resolve_scope(build_trigger_event("@stackpilot 帮我 review 这个 PR https://github.com/openai/demo/pull/12"))
    )
    assert review_state is not None
    assert review_state.published_review_ref == "https://github.com/openai/demo/pull/12#issuecomment-1"
    assert review_state.findings[0].outcome_status is ReviewOutcomeStatus.PUBLISHED
    assert review_state.findings[0].outcome_source is ReviewOutcomeSource.GITHUB_PUBLISH
    records = interaction_recorder.list_thread_records(scope)
    assert records[-1].event_type is InteractionEventType.ACTION_EXECUTED


@pytest.mark.anyio
async def test_code_review_flow_syncs_github_comment_outcome_into_review_state(tmp_path: Path) -> None:
    review_flow, feishu_client, github_client, _, interaction_recorder, memory_service = build_review_flow(
        tmp_path=tmp_path,
        llm_response=load_text("analysis", "code_review_success.json"),
        github_patch=INLINE_PATCH_MESSAGE.split("```diff", maxsplit=1)[1].split("```", maxsplit=1)[0].strip(),
        publish_url="https://github.com/openai/demo/pull/12#issuecomment-1",
        issue_comments=[
            GitHubIssueComment(
                comment_id=101,
                html_url="https://github.com/openai/demo/pull/12#issuecomment-1",
                body="## AI Code Review Draft",
                author_login="stackpilot-bot",
                created_at=datetime.fromisoformat("2026-04-11T02:05:00+00:00"),
            ),
            GitHubIssueComment(
                comment_id=102,
                html_url="https://github.com/openai/demo/pull/12#issuecomment-2",
                body="Addressed F1 in the follow-up patch.",
                author_login="alice",
                created_at=datetime.fromisoformat("2026-04-11T02:10:00+00:00"),
            ),
        ],
    )

    review_event = build_trigger_event("@stackpilot 帮我 review 这个 PR https://github.com/openai/demo/pull/12")
    await review_flow.process_trigger(
        trigger_command=TriggerCommand.REVIEW_CODE,
        trigger_event=review_event,
    )
    await review_flow.process_approval(
        trigger_event=build_trigger_event("批准动作 R1").model_copy(update={"message_id": "om_review_approve_2"}),
    )
    handled = await review_flow.process_outcome_sync(
        trigger_event=build_trigger_event("@stackpilot 同步 review 结果").model_copy(
            update={"message_id": "om_review_sync_1"}
        ),
    )

    assert handled is True
    assert github_client.list_comment_calls == ["https://github.com/openai/demo/pull/12"]
    assert "GitHub review 结果已同步" in feishu_client.reply_calls[-1][3]
    review_state = memory_service.load_review_state(memory_service.resolve_scope(review_event))
    assert review_state is not None
    assert review_state.findings[0].outcome_status is ReviewOutcomeStatus.ACCEPTED
    assert review_state.findings[0].outcome_source is ReviewOutcomeSource.GITHUB_COMMENT
    assert review_state.findings[0].outcome_source_ref == "https://github.com/openai/demo/pull/12#issuecomment-2"
    scope = ActionScope(tenant_id="oc_xxx", thread_id="omt_review")
    records = interaction_recorder.list_thread_records(scope)
    assert records[-1].event_type is InteractionEventType.REVIEW_OUTCOME_RECORDED
    assert records[-1].payload["outcome_status"] == "accepted"


@pytest.mark.anyio
async def test_code_review_flow_sync_marks_unresolved_without_explicit_github_signal(tmp_path: Path) -> None:
    review_flow, feishu_client, _, _, interaction_recorder, memory_service = build_review_flow(
        tmp_path=tmp_path,
        llm_response=load_text("analysis", "code_review_success.json"),
        github_patch=INLINE_PATCH_MESSAGE.split("```diff", maxsplit=1)[1].split("```", maxsplit=1)[0].strip(),
        publish_url="https://github.com/openai/demo/pull/12#issuecomment-1",
        issue_comments=[
            GitHubIssueComment(
                comment_id=101,
                html_url="https://github.com/openai/demo/pull/12#issuecomment-1",
                body="## AI Code Review Draft",
                author_login="stackpilot-bot",
                created_at=datetime.fromisoformat("2026-04-11T02:05:00+00:00"),
            )
        ],
    )

    review_event = build_trigger_event("@stackpilot 帮我 review 这个 PR https://github.com/openai/demo/pull/12")
    await review_flow.process_trigger(
        trigger_command=TriggerCommand.REVIEW_CODE,
        trigger_event=review_event,
    )
    await review_flow.process_approval(
        trigger_event=build_trigger_event("批准动作 R1").model_copy(update={"message_id": "om_review_approve_3"}),
    )
    handled = await review_flow.process_outcome_sync(
        trigger_event=build_trigger_event("@stackpilot 同步 review 结果").model_copy(
            update={"message_id": "om_review_sync_2"}
        ),
    )

    assert handled is True
    assert "仍未明确处理: 1" in feishu_client.reply_calls[-1][3]
    review_state = memory_service.load_review_state(memory_service.resolve_scope(review_event))
    assert review_state is not None
    assert review_state.findings[0].outcome_status is ReviewOutcomeStatus.UNRESOLVED
    assert review_state.findings[0].outcome_source is ReviewOutcomeSource.GITHUB_SYNC
    scope = ActionScope(tenant_id="oc_xxx", thread_id="omt_review")
    records = interaction_recorder.list_thread_records(scope)
    assert any(record.payload.get("outcome_status") == "unresolved" for record in records)


@pytest.mark.anyio
async def test_code_review_flow_records_feedback_and_updates_preferences(tmp_path: Path) -> None:
    review_flow, feishu_client, _, _, interaction_recorder, memory_service = build_review_flow(
        tmp_path=tmp_path,
        llm_response=load_text("analysis", "code_review_success.json"),
    )
    security_message = (
        "@stackpilot 按安全重点审一下这个 diff\n"
        "```diff\n"
        "diff --git a/app/services/tickets.py b/app/services/tickets.py\n"
        "--- a/app/services/tickets.py\n"
        "+++ b/app/services/tickets.py\n"
        "@@ -10,2 +10,4 @@ def build_ticket(payload):\n"
        "+title = payload.get(\"title\").strip()\n"
        "```\n"
    )

    await review_flow.process_trigger(
        trigger_command=TriggerCommand.REVIEW_CODE,
        trigger_event=build_trigger_event(security_message),
    )
    handled = await review_flow.process_feedback(
        trigger_event=build_trigger_event("采纳建议 F1").model_copy(
            update={"message_id": "om_review_feedback_1"}
        ),
    )

    assert handled is True
    assert "已记录为采纳" in feishu_client.reply_calls[-1][3]
    scope = ActionScope(tenant_id="oc_xxx", thread_id="omt_review")
    records = interaction_recorder.list_thread_records(scope)
    assert records[-1].event_type is InteractionEventType.REVIEW_FEEDBACK_RECORDED
    review_state = memory_service.load_review_state(memory_service.resolve_scope(build_trigger_event(security_message)))
    assert review_state is not None
    assert review_state.findings[0].feedback_status is ReviewFeedbackStatus.ACCEPTED
    user_memory = memory_service.load_user_memory(memory_service.resolve_scope(build_trigger_event(security_message)))
    review_preferences = user_memory.get("review_preferences")
    assert isinstance(review_preferences, dict)
    assert review_preferences.get("accepted_focus_counts", {}).get("security") == 1


@pytest.mark.anyio
async def test_code_review_flow_reuses_preferred_focus_after_repeated_explicit_requests(tmp_path: Path) -> None:
    review_flow, _, _, _, _, memory_service = build_review_flow(
        tmp_path=tmp_path,
        llm_response=load_text("analysis", "code_review_success.json"),
    )
    security_message = (
        "@stackpilot 按安全审一下这个 diff\n"
        "```diff\n"
        "diff --git a/app/services/tickets.py b/app/services/tickets.py\n"
        "--- a/app/services/tickets.py\n"
        "+++ b/app/services/tickets.py\n"
        "@@ -10,2 +10,4 @@ def build_ticket(payload):\n"
        "+title = payload.get(\"title\").strip()\n"
        "```\n"
    )

    await review_flow.process_trigger(
        trigger_command=TriggerCommand.REVIEW_CODE,
        trigger_event=build_trigger_event(security_message).model_copy(update={"message_id": "om_review_pref_1"}),
    )
    await review_flow.process_trigger(
        trigger_command=TriggerCommand.REVIEW_CODE,
        trigger_event=build_trigger_event(security_message).model_copy(update={"message_id": "om_review_pref_2", "thread_id": "omt_review_pref_2"}),
    )
    await review_flow.process_trigger(
        trigger_command=TriggerCommand.REVIEW_CODE,
        trigger_event=build_trigger_event(INLINE_PATCH_MESSAGE).model_copy(update={"message_id": "om_review_pref_3", "thread_id": "omt_review_pref_3"}),
    )

    user_memory = memory_service.load_user_memory(memory_service.resolve_scope(build_trigger_event(INLINE_PATCH_MESSAGE)))
    review_preferences = user_memory.get("review_preferences")
    assert isinstance(review_preferences, dict)
    assert review_preferences.get("preferred_focus_areas") == ["security"]

    review_state = memory_service.load_review_state(
        memory_service.resolve_scope(
            build_trigger_event(INLINE_PATCH_MESSAGE).model_copy(
                update={"message_id": "om_review_pref_3", "thread_id": "omt_review_pref_3"}
            )
        )
    )
    assert review_state is not None
    assert [item.value for item in review_state.focus_areas] == ["security"]


@pytest.mark.anyio
async def test_code_review_flow_prefers_canonical_defaults_and_policy_docs_over_org_memory(
    tmp_path: Path,
) -> None:
    knowledge_dir = tmp_path / "knowledge"
    shutil.copytree(FIXTURES_DIR / "knowledge", knowledge_dir)
    tenant_dir = knowledge_dir / "canonical" / "oc_xxx"
    tenant_dir.mkdir(parents=True, exist_ok=True)
    (tenant_dir / "team-review.canonical.json").write_text(
        json.dumps(
            {
                "convention_id": "team-review",
                "title": "Team Review Defaults",
                "status": "approved",
                "review_defaults": {
                    "default_focus_areas": ["security"],
                },
                "policy_documents": [
                    {
                        "doc_id": "review-security-policy",
                        "title": "Approved Security Review Policy",
                        "content": "Always inspect auth, permission, and input-validation changes first.",
                        "scope": "review",
                        "source_uri": "canonical://oc_xxx/team-review/review-security-policy",
                        "tags": ["policy", "review", "security"],
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    review_flow, _, _, _, interaction_recorder, memory_service = build_review_flow(
        tmp_path=tmp_path,
        llm_response=load_text("analysis", "code_review_success.json"),
        knowledge_dir=knowledge_dir,
    )
    memory_service.save_org_memory_for_tenant(
        "oc_xxx",
        {
            "review_defaults": {
                "default_focus_areas": ["bug_risk"],
            }
        },
    )

    await review_flow.process_trigger(
        trigger_command=TriggerCommand.REVIEW_CODE,
        trigger_event=build_trigger_event(INLINE_PATCH_MESSAGE).model_copy(
            update={"message_id": "om_review_canonical_1", "thread_id": "omt_review_canonical"}
        ),
    )

    review_state = memory_service.load_review_state(
        memory_service.resolve_scope(
            build_trigger_event(INLINE_PATCH_MESSAGE).model_copy(
                update={"message_id": "om_review_canonical_1", "thread_id": "omt_review_canonical"}
            )
        )
    )
    assert review_state is not None
    assert [item.value for item in review_state.focus_areas] == ["security"]

    scope = ActionScope(tenant_id="oc_xxx", thread_id="omt_review_canonical")
    records = interaction_recorder.list_thread_records(scope)
    assert "canonical://oc_xxx/team-review/review-security-policy" in records[0].payload["policy_refs"]


@pytest.mark.anyio
async def test_code_review_flow_uses_org_default_focus_when_user_has_no_preference(tmp_path: Path) -> None:
    review_flow, _, _, _, _, memory_service = build_review_flow(
        tmp_path=tmp_path,
        llm_response=load_text("analysis", "code_review_success.json"),
    )
    memory_service.save_org_memory_for_tenant(
        "oc_xxx",
        {
            "review_defaults": {
                "default_focus_areas": ["security"],
            }
        },
    )

    await review_flow.process_trigger(
        trigger_command=TriggerCommand.REVIEW_CODE,
        trigger_event=build_trigger_event(INLINE_PATCH_MESSAGE).model_copy(
            update={"message_id": "om_review_org_1", "thread_id": "omt_review_org"}
        ),
    )

    review_state = memory_service.load_review_state(
        memory_service.resolve_scope(
            build_trigger_event(INLINE_PATCH_MESSAGE).model_copy(
                update={"message_id": "om_review_org_1", "thread_id": "omt_review_org"}
            )
        )
    )
    assert review_state is not None
    assert [item.value for item in review_state.focus_areas] == ["security"]
