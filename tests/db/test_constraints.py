from datetime import UTC, datetime

import pytest
from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError

from app.db.models import AgentRun, RunStatus, User
from app.db.session import create_session_factory


def test_database_allows_only_one_active_run_per_user(db_engine: Engine) -> None:
    sessions = create_session_factory(db_engine)
    with sessions.begin() as session:
        session.add(
            User(
                id="user-1",
                identity="Candidate",
                email="candidate@example.com",
                timezone="UTC",
            )
        )
        session.add(
            AgentRun(
                id="run-1",
                user_id="user-1",
                status=RunStatus.PENDING,
                model="fake-model",
            )
        )

    with pytest.raises(IntegrityError), sessions.begin() as session:
        session.add(
            AgentRun(
                id="run-2",
                user_id="user-1",
                status=RunStatus.RUNNING,
                model="fake-model",
            )
        )

    with sessions.begin() as session:
        first = session.get(AgentRun, "run-1")
        assert first is not None
        first.status = RunStatus.COMPLETED
        first.finished_at = datetime.now(UTC)

    with sessions.begin() as session:
        session.add(
            AgentRun(
                id="run-2",
                user_id="user-1",
                status=RunStatus.PENDING,
                model="fake-model",
            )
        )
