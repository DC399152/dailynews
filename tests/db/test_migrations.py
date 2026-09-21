from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def test_initial_migration_upgrades_and_downgrades(tmp_path: Path) -> None:
    database_path = tmp_path / "migration.db"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")
    config.attributes["skip_settings_url"] = True

    command.upgrade(config, "head")

    engine = create_engine(f"sqlite:///{database_path}")
    assert set(inspect(engine).get_table_names()) == {
        "agent_runs",
        "alembic_version",
        "digests",
        "subscriptions",
        "tool_calls",
        "users",
    }
    assert {index["name"] for index in inspect(engine).get_indexes("agent_runs")} == {
        "ix_agent_runs_user_created",
        "uq_agent_runs_active_user",
    }
    engine.dispose()

    command.downgrade(config, "base")
    engine = create_engine(f"sqlite:///{database_path}")
    assert inspect(engine).get_table_names() == ["alembic_version"]
    engine.dispose()
