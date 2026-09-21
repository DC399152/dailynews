from pathlib import Path

import pytest
from sqlalchemy import Engine

from app.db.models import Base
from app.db.session import create_database_engine
from app.settings import Settings


@pytest.fixture
def test_settings(tmp_path: Path) -> Settings:
    return Settings(
        app_env="test",
        app_database_url=f"sqlite:///{tmp_path / 'test.db'}",
        app_workspace_dir=tmp_path / "workspace",
        llm_model="fake-model",
        scheduler_enabled=False,
    )


@pytest.fixture
def db_engine(test_settings: Settings) -> Engine:
    engine = create_database_engine(test_settings.app_database_url)
    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()
