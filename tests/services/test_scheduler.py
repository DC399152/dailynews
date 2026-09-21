from datetime import time
from types import SimpleNamespace

from sqlalchemy import Engine

from app.db.models import Subscription, User
from app.db.session import create_session_factory
from app.services.runs import RunStartError
from app.services.scheduler import DailyDigestScheduler


class FakeCoordinator:
    def __init__(self, *, error: RunStartError | None = None) -> None:
        self.error = error
        self.requested_users: list[str] = []

    def create_run(self, user_id: str):
        self.requested_users.append(user_id)
        if self.error is not None:
            raise self.error
        return SimpleNamespace(id="scheduled-run")


class FakeDigestService:
    def __init__(self) -> None:
        self.executed_runs: list[str] = []

    async def execute_run(self, run_id: str) -> None:
        self.executed_runs.append(run_id)


def add_subscription(engine: Engine, *, enabled: bool = True) -> None:
    sessions = create_session_factory(engine)
    with sessions.begin() as session:
        session.add(
            User(
                id="user-1",
                identity="Candidate",
                email="candidate@example.com",
                timezone="Asia/Shanghai",
            )
        )
        session.add(
            Subscription(
                user_id="user-1",
                topics=["agents"],
                delivery_time=time(8, 45),
                enabled=enabled,
            )
        )


def test_scheduler_uses_user_timezone_and_removes_disabled_job(db_engine: Engine) -> None:
    add_subscription(db_engine)
    sessions = create_session_factory(db_engine)
    scheduler = DailyDigestScheduler(
        sessions=sessions,
        coordinator=FakeCoordinator(),  # type: ignore[arg-type]
        digest_service=FakeDigestService(),  # type: ignore[arg-type]
    )
    scheduler.start()
    try:
        job = scheduler.get_job("user-1")
        assert job is not None
        assert str(job.trigger.timezone) == "Asia/Shanghai"
        assert "hour='8'" in str(job.trigger)
        assert "minute='45'" in str(job.trigger)

        with sessions.begin() as session:
            subscription = session.get(Subscription, "user-1")
            assert subscription is not None
            subscription.enabled = False
        scheduler.sync_user("user-1")
        assert scheduler.get_job("user-1") is None
    finally:
        scheduler.shutdown()


def test_scheduled_job_creates_and_executes_run(db_engine: Engine) -> None:
    coordinator = FakeCoordinator()
    service = FakeDigestService()
    scheduler = DailyDigestScheduler(
        sessions=create_session_factory(db_engine),
        coordinator=coordinator,  # type: ignore[arg-type]
        digest_service=service,  # type: ignore[arg-type]
    )

    scheduler._execute_scheduled_run("user-1")

    assert coordinator.requested_users == ["user-1"]
    assert service.executed_runs == ["scheduled-run"]


def test_scheduled_job_skips_expected_active_run_conflict(db_engine: Engine) -> None:
    coordinator = FakeCoordinator(error=RunStartError("run_already_active", "Already running"))
    service = FakeDigestService()
    scheduler = DailyDigestScheduler(
        sessions=create_session_factory(db_engine),
        coordinator=coordinator,  # type: ignore[arg-type]
        digest_service=service,  # type: ignore[arg-type]
    )

    scheduler._execute_scheduled_run("user-1")

    assert coordinator.requested_users == ["user-1"]
    assert service.executed_runs == []
