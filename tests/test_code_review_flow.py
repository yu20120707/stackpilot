import json
from datetime import datetime
from pathlib import Path

import pytest

from app.clients.feishu_client import FeishuClient
from app.models.contracts import (
    ActionScope,
    FeishuReplySendResult,
    InteractionEventType,
    NormalizedFeishuMessageEvent,
    TriggerCommand,
)
from app.services.kernel.audit_log_service import AuditLogService
from app.services.kernel.action_queue_service import ActionQueueService
from app.services.kernel.interaction_recorder import InteractionRecorder
from app.services.knowledge_base import KnowledgeBase
from app.services.review.diff_reader import DiffReader
from app.services.review.flow import CodeReviewFlow
from app.services.review.policy_service import ReviewPolicyService
from app.services.review.publish_service import ReviewPublishService
from app.services.review.renderer import ReviewRenderer
from app.services.review.service import ReviewService
from app.services.skill_miner import SkillMiner
from app.services.skill_registry import SkillRegistry


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
    def __init__(self, *, patch_text: str | None = None, publish_url: str | None = None) -> None:
        self.patch_text = patch_text
        self.publish_url = publish_url
        self.fetch_calls: list[str] = []
        self.publish_calls: list[tuple[str, str]] = []

    async def fetch_pull_request_diff(self, pull_request_url: str) -> str | None:
        self.fetch_calls.append(pull_request_url)
        return self.patch_text

    async def publish_issue_comment(self, *, pull_request_url: str, body: str) -> str | None:
        self.publish_calls.append((pull_request_url, body))
        return self.publish_url


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
    reply_success: bool = True,
) -> tuple[CodeReviewFlow, FakeReviewFeishuClient, FakeGitHubReviewClient, ActionQueueService, InteractionRecorder]:
    feishu_client = FakeReviewFeishuClient(reply_success=reply_success)
    llm_client = FakeLLMClient(llm_response)
    github_client = FakeGitHubReviewClient(
        patch_text=github_patch,
        publish_url=publish_url,
    )
    interaction_recorder, skill_miner = build_growth_services(tmp_path)
    action_queue_service = ActionQueueService(tmp_path / "actions")
    review_renderer = ReviewRenderer()
    review_flow = CodeReviewFlow(
        feishu_client=feishu_client,
        github_review_client=github_client,
        diff_reader=DiffReader(),
        review_policy_service=ReviewPolicyService(KnowledgeBase(FIXTURES_DIR / "knowledge", max_hits=3)),
        review_service=ReviewService(llm_client),
        review_renderer=review_renderer,
        review_publish_service=ReviewPublishService(
            action_queue_service=action_queue_service,
            github_review_client=github_client,
            review_renderer=review_renderer,
        ),
        interaction_recorder=interaction_recorder,
        skill_miner=skill_miner,
    )
    return review_flow, feishu_client, github_client, action_queue_service, interaction_recorder


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
async def test_code_review_flow_reviews_inline_patch_and_records_draft(tmp_path: Path) -> None:
    review_flow, feishu_client, _, _, interaction_recorder = build_review_flow(
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


@pytest.mark.anyio
async def test_code_review_flow_fetches_github_pr_and_prepares_publish_action(tmp_path: Path) -> None:
    patch_text = load_text("analysis", "code_review_success.json")
    _ = patch_text
    review_flow, feishu_client, github_client, action_queue_service, _ = build_review_flow(
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
    review_flow, feishu_client, github_client, action_queue_service, interaction_recorder = build_review_flow(
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
    assert "https://github.com/openai/demo/pull/12#issuecomment-1" in feishu_client.reply_calls[1][3]
    records = interaction_recorder.list_thread_records(scope)
    assert records[-1].event_type is InteractionEventType.ACTION_EXECUTED
