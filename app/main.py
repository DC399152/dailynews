from collections.abc import Callable

from fastapi import FastAPI
from sqlalchemy import Engine

from app.agent.model import ModelClient, OpenAICompatibleModelClient
from app.api.errors import install_error_handlers
from app.api.routes import router
from app.db.session import create_database_engine, create_session_factory
from app.services.digest import DigestService
from app.settings import Settings, get_settings


def create_app(
    *,
    settings: Settings | None = None,
    engine: Engine | None = None,
    model_factory: Callable[[], ModelClient] | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    engine = engine or create_database_engine(settings.app_database_url)
    sessions = create_session_factory(engine)
    if model_factory is None:

        def model_factory() -> ModelClient:
            return OpenAICompatibleModelClient(
                api_key=settings.llm_api_key,
                base_url=settings.llm_base_url,
                model=settings.llm_model,
            )

    application = FastAPI(
        title="AI Daily Brief",
        summary="A model-driven personal AI news briefing agent.",
        version="0.1.0",
    )
    application.state.settings = settings
    application.state.engine = engine
    application.state.sessions = sessions
    application.state.digest_service = DigestService(
        settings=settings,
        sessions=sessions,
        model_factory=model_factory,
    )
    install_error_handlers(application)
    application.include_router(router)

    @application.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "environment": settings.app_env}

    return application


app = create_app()
