from fastapi import FastAPI

from app.api.feishu import router as feishu_router
from app.core.config import get_settings
from app.core.logging import configure_logging


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="feishu-incident-copilot",
        version="0.1.0",
    )

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(feishu_router)
    return app


app = create_app()
