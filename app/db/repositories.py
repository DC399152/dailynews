from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.db.models import Subscription, User
from app.db.session import SessionFactory
from app.tools.subscription import SubscriptionProfile


class SQLAlchemySubscriptionProvider:
    """Database-backed provider implementing the Agent tool's stable interface."""

    def __init__(self, sessions: SessionFactory) -> None:
        self._sessions = sessions

    async def get(self, user_id: str) -> SubscriptionProfile | None:
        return await asyncio.to_thread(self._get, user_id)

    def _get(self, user_id: str) -> SubscriptionProfile | None:
        with self._sessions() as session:
            statement = (
                select(User, Subscription)
                .join(Subscription, Subscription.user_id == User.id)
                .where(User.id == user_id, Subscription.enabled.is_(True))
            )
            row = session.execute(statement).one_or_none()
            if row is None:
                return None
            user, subscription = row
            return SubscriptionProfile(
                user_id=user.id,
                identity=user.identity,
                topics=list(subscription.topics),
                keywords=list(subscription.keywords),
                excluded_keywords=list(subscription.excluded_keywords),
                email=user.email,
                timezone=user.timezone,
            )
