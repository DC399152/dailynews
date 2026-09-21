from __future__ import annotations

import asyncio
import logging
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from app.db.models import Subscription, User
from app.db.session import SessionFactory
from app.services.digest import DigestService
from app.services.runs import DigestRunCoordinator, RunStartError

logger = logging.getLogger(__name__)


class DailyDigestScheduler:
    def __init__(
        self,
        *,
        sessions: SessionFactory,
        coordinator: DigestRunCoordinator,
        digest_service: DigestService,
        enabled: bool = True,
        scheduler: BackgroundScheduler | None = None,
    ) -> None:
        self._sessions = sessions
        self._coordinator = coordinator
        self._digest_service = digest_service
        self._enabled = enabled
        self._scheduler = scheduler or BackgroundScheduler(timezone="UTC")

    @property
    def running(self) -> bool:
        return self._scheduler.running

    def start(self) -> None:
        if not self._enabled or self._scheduler.running:
            return
        self.sync_all()
        self._scheduler.start()

    def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)

    def sync_all(self) -> None:
        if not self._enabled:
            return
        with self._sessions() as session:
            user_ids = list(session.scalars(select(User.id)))
        for user_id in user_ids:
            self.sync_user(user_id)

    def sync_user(self, user_id: str) -> None:
        if not self._enabled:
            return
        job_id = self._job_id(user_id)
        with self._sessions() as session:
            row = session.execute(
                select(User.timezone, Subscription.delivery_time, Subscription.enabled)
                .join(Subscription, Subscription.user_id == User.id)
                .where(User.id == user_id)
            ).one_or_none()
        if row is None or not row.enabled:
            self._remove_job(job_id)
            return

        delivery_time = row.delivery_time
        trigger = CronTrigger(
            hour=delivery_time.hour,
            minute=delivery_time.minute,
            timezone=ZoneInfo(row.timezone),
        )
        self._scheduler.add_job(
            self._execute_scheduled_run,
            trigger=trigger,
            args=(user_id,),
            id=job_id,
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=3600,
        )

    def get_job(self, user_id: str):
        return self._scheduler.get_job(self._job_id(user_id))

    def _execute_scheduled_run(self, user_id: str) -> None:
        try:
            run = self._coordinator.create_run(user_id)
        except RunStartError as exc:
            logger.info("Skipping scheduled run for %s: %s", user_id, exc.code)
            return
        asyncio.run(self._digest_service.execute_run(run.id))

    def _remove_job(self, job_id: str) -> None:
        if self._scheduler.get_job(job_id) is not None:
            self._scheduler.remove_job(job_id)

    @staticmethod
    def _job_id(user_id: str) -> str:
        return f"daily-digest:{user_id}"
