from dataclasses import dataclass

from fastapi import FastAPI

from app.clients.feishu_client import FeishuClient, FeishuClientConfig
from app.clients.llm_client import LLMClient, LLMClientConfig
from app.api.feishu import router as feishu_router
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.services.analysis_service import AnalysisService
from app.services.feishu_live_flow import FeishuLiveFlow
from app.services.incident_action_service import IncidentActionService
from app.services.kernel.action_queue_service import ActionQueueService
from app.services.kernel.memory_service import MemoryService
from app.services.knowledge_base import KnowledgeBase
from app.services.postmortem_renderer import PostmortemRenderer
from app.services.postmortem_service import PostmortemService
from app.services.reply_renderer import ReplyRenderer
from app.services.task_sync_service import TaskSyncService
from app.services.thread_reader import ThreadReader


@dataclass(slots=True)
class AppServices:
    settings: Settings
    feishu_client: FeishuClient
    llm_client: LLMClient
    memory_service: MemoryService
    feishu_live_flow: FeishuLiveFlow

    async def aclose(self) -> None:
        await self.feishu_client.aclose()
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
    memory_service = MemoryService(settings.resolved_memory_dir)
    action_queue_service = ActionQueueService(settings.resolved_action_dir)
    thread_reader = ThreadReader(
        feishu_client,
        memory_service=memory_service,
        max_thread_messages=settings.max_thread_messages,
    )
    knowledge_base = KnowledgeBase(
        settings.resolved_knowledge_dir,
        max_hits=settings.max_knowledge_hits,
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
    )
    reply_renderer = ReplyRenderer()
    feishu_live_flow = FeishuLiveFlow(
        feishu_client=feishu_client,
        thread_reader=thread_reader,
        memory_service=memory_service,
        knowledge_base=knowledge_base,
        analysis_service=analysis_service,
        reply_renderer=reply_renderer,
        incident_action_service=incident_action_service,
    )
    return AppServices(
        settings=settings,
        feishu_client=feishu_client,
        llm_client=llm_client,
        memory_service=memory_service,
        feishu_live_flow=feishu_live_flow,
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
