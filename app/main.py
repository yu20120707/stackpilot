from dataclasses import dataclass

from fastapi import FastAPI

from app.clients.feishu_client import FeishuClient, FeishuClientConfig
from app.clients.github_review_client import GitHubReviewClient, GitHubReviewClientConfig
from app.clients.llm_client import LLMClient, LLMClientConfig
from app.api.feishu import router as feishu_router
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.services.analysis_service import AnalysisService
from app.services.convention_promotion_service import ConventionPromotionService
from app.services.feishu_live_flow import FeishuLiveFlow
from app.services.incident_action_service import IncidentActionService
from app.services.kernel.audit_log_service import AuditLogService
from app.services.kernel.action_queue_service import ActionQueueService
from app.services.kernel.canonical_convention_service import CanonicalConventionService
from app.services.kernel.interaction_recorder import InteractionRecorder
from app.services.kernel.memory_service import MemoryService
from app.services.kernel.org_convention_service import OrgConventionService
from app.services.knowledge_base import KnowledgeBase
from app.services.postmortem_renderer import PostmortemRenderer
from app.services.postmortem_service import PostmortemService
from app.services.reply_renderer import ReplyRenderer
from app.services.review.diff_reader import DiffReader
from app.services.review.flow import CodeReviewFlow
from app.services.review.preference_service import ReviewPreferenceService
from app.services.review.policy_service import ReviewPolicyService
from app.services.review.publish_service import ReviewPublishService
from app.services.review.renderer import ReviewRenderer
from app.services.review.service import ReviewService
from app.services.skill_miner import SkillMiner
from app.services.skill_registry import SkillRegistry
from app.services.task_sync_service import TaskSyncService
from app.services.thread_reader import ThreadReader
from app.services.workflow_router import WorkflowRouter


@dataclass(slots=True)
class AppServices:
    settings: Settings
    feishu_client: FeishuClient
    github_review_client: GitHubReviewClient
    llm_client: LLMClient
    memory_service: MemoryService
    feishu_live_flow: FeishuLiveFlow
    code_review_flow: CodeReviewFlow
    workflow_router: WorkflowRouter

    async def aclose(self) -> None:
        await self.feishu_client.aclose()
        await self.github_review_client.aclose()
        await self.llm_client.aclose()


def build_services(settings: Settings) -> AppServices:
    feishu_client = FeishuClient(
        FeishuClientConfig(
            base_url=settings.feishu_base_url,
            tenant_access_token=None,
            app_id=settings.feishu_app_id,
            app_secret=settings.feishu_app_secret,
            timeout_seconds=settings.feishu_timeout_seconds,
        )
    )
    llm_client = LLMClient(
        LLMClientConfig(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            timeout_seconds=settings.llm_timeout_seconds,
        )
    )
    github_review_client = GitHubReviewClient(
        GitHubReviewClientConfig(
            base_url=settings.github_api_base_url,
            token=settings.github_token,
            timeout_seconds=settings.github_timeout_seconds,
        )
    )
    memory_service = MemoryService(settings.resolved_memory_dir)
    action_queue_service = ActionQueueService(settings.resolved_action_dir)
    audit_log_service = AuditLogService(settings.resolved_records_dir)
    canonical_convention_service = CanonicalConventionService(
        settings.resolved_knowledge_dir,
        audit_log_service=audit_log_service,
    )
    org_convention_service = OrgConventionService(
        memory_service,
        canonical_convention_service=canonical_convention_service,
    )
    interaction_recorder = InteractionRecorder(
        settings.resolved_records_dir,
        audit_log_service=audit_log_service,
    )
    skill_registry = SkillRegistry(
        settings.resolved_skills_dir,
        audit_log_service=audit_log_service,
    )
    skill_miner = SkillMiner(
        interaction_recorder=interaction_recorder,
        skill_registry=skill_registry,
    )
    thread_reader = ThreadReader(
        feishu_client,
        memory_service=memory_service,
        max_thread_messages=settings.max_thread_messages,
    )
    knowledge_base = KnowledgeBase(
        settings.resolved_knowledge_dir,
        max_hits=settings.max_knowledge_hits,
        canonical_convention_service=canonical_convention_service,
    )
    analysis_service = AnalysisService(llm_client)
    task_sync_service = TaskSyncService()
    postmortem_service = PostmortemService(llm_client)
    postmortem_renderer = PostmortemRenderer()
    incident_action_service = IncidentActionService(
        action_queue_service=action_queue_service,
        task_sync_service=task_sync_service,
        postmortem_service=postmortem_service,
        postmortem_renderer=postmortem_renderer,
        org_convention_service=org_convention_service,
    )
    convention_promotion_service = ConventionPromotionService(
        action_queue_service=action_queue_service,
        skill_registry=skill_registry,
        canonical_convention_service=canonical_convention_service,
    )
    reply_renderer = ReplyRenderer()
    review_renderer = ReviewRenderer()
    review_service = ReviewService(llm_client)
    review_policy_service = ReviewPolicyService(knowledge_base)
    review_preference_service = ReviewPreferenceService(
        memory_service,
        org_convention_service=org_convention_service,
    )
    review_publish_service = ReviewPublishService(
        action_queue_service=action_queue_service,
        github_review_client=github_review_client,
        review_renderer=review_renderer,
    )
    feishu_live_flow = FeishuLiveFlow(
        feishu_client=feishu_client,
        thread_reader=thread_reader,
        memory_service=memory_service,
        knowledge_base=knowledge_base,
        analysis_service=analysis_service,
        reply_renderer=reply_renderer,
        incident_action_service=incident_action_service,
        convention_promotion_service=convention_promotion_service,
        interaction_recorder=interaction_recorder,
        skill_miner=skill_miner,
    )
    code_review_flow = CodeReviewFlow(
        feishu_client=feishu_client,
        github_review_client=github_review_client,
        diff_reader=DiffReader(),
        review_policy_service=review_policy_service,
        review_preference_service=review_preference_service,
        review_service=review_service,
        review_renderer=review_renderer,
        review_publish_service=review_publish_service,
        memory_service=memory_service,
        interaction_recorder=interaction_recorder,
        skill_miner=skill_miner,
    )
    workflow_router = WorkflowRouter(
        incident_flow=feishu_live_flow,
        code_review_flow=code_review_flow,
    )
    return AppServices(
        settings=settings,
        feishu_client=feishu_client,
        github_review_client=github_review_client,
        llm_client=llm_client,
        memory_service=memory_service,
        feishu_live_flow=feishu_live_flow,
        code_review_flow=code_review_flow,
        workflow_router=workflow_router,
    )


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    services = build_services(settings)

    app = FastAPI(
        title="stackpilot",
        version="0.1.0",
    )
    app.state.settings = settings
    app.state.services = services

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.on_event("shutdown")
    async def shutdown_services() -> None:
        await services.aclose()

    app.include_router(feishu_router)
    return app


app = create_app()
