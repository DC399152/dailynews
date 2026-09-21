from fastapi import FastAPI

from app.settings import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title="AI Daily Brief",
        summary="A model-driven personal AI news briefing agent.",
        version="0.1.0",
    )

    @application.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "environment": settings.app_env}

    return application


app = create_app()
