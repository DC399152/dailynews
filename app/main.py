from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import Engine

from app.agent.model import ModelClient, OpenAICompatibleModelClient
from app.api.errors import install_error_handlers
from app.api.routes import router
from app.db.session import create_database_engine, create_session_factory
from app.services.digest import DigestService, ToolRegistryFactory
from app.services.runs import DigestRunCoordinator
from app.services.scheduler import DailyDigestScheduler
from app.settings import Settings, get_settings
from app.web.routes import router as web_router


def create_app(
    *,
    settings: Settings | None = None,
    engine: Engine | None = None,
    model_factory: Callable[[], ModelClient] | None = None,
    tool_registry_factory: ToolRegistryFactory | None = None,
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

    digest_service = DigestService(
        settings=settings,
        sessions=sessions,
        model_factory=model_factory,
        tool_registry_factory=tool_registry_factory,
    )
    run_coordinator = DigestRunCoordinator(
        sessions=sessions,
        digest_service=digest_service,
    )
    scheduler = DailyDigestScheduler(
        sessions=sessions,
        coordinator=run_coordinator,
        digest_service=digest_service,
        enabled=settings.scheduler_enabled,
    )

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        del application
        scheduler.start()
        try:
            yield
        finally:
            scheduler.shutdown()

    application = FastAPI(
        title="AI Daily Brief",
        summary="A model-driven personal AI news briefing agent.",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.state.settings = settings
    application.state.engine = engine
    application.state.sessions = sessions
    application.state.digest_service = digest_service
    application.state.run_coordinator = run_coordinator
    application.state.scheduler = scheduler
    install_error_handlers(application)
    application.include_router(router)
    application.include_router(web_router)
    application.mount(
        "/static",
        StaticFiles(directory=Path(__file__).parent / "static"),
        name="static",
    )

    @application.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "environment": settings.app_env}

    return application


app = create_app()
