from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db.models import AgentRun, RunStatus, Subscription, User
from app.db.session import SessionFactory
from app.services.digest import DigestService


class RunStartError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class DigestRunCoordinator:
    """Creates runs consistently for HTTP requests and scheduled jobs."""

    def __init__(self, *, sessions: SessionFactory, digest_service: DigestService) -> None:
        self._sessions = sessions
        self._digest_service = digest_service

    def create_run(self, user_id: str) -> AgentRun:
        with self._sessions() as session:
            if session.get(User, user_id) is None:
                raise RunStartError("user_not_found", f"User does not exist: {user_id}")
            subscription = session.get(Subscription, user_id)
            if subscription is None or not subscription.enabled:
                raise RunStartError(
                    "subscription_unavailable",
                    "An enabled subscription is required to start a digest",
                )
            active = session.scalar(
                select(AgentRun).where(
                    AgentRun.user_id == user_id,
                    AgentRun.status.in_((RunStatus.PENDING, RunStatus.RUNNING)),
                )
            )
            if active is not None:
                raise RunStartError(
                    "run_already_active",
                    "User already has an active digest run",
                )

            run = AgentRun(
                user_id=user_id,
                status=RunStatus.PENDING,
                model=self._digest_service.model_name,
            )
            session.add(run)
            try:
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                raise RunStartError(
                    "run_already_active",
                    "User already has an active digest run",
                ) from exc
            session.refresh(run)
            return run
