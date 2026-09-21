from datetime import time

import pytest
from sqlalchemy import Engine

from app.db.models import Subscription, User
from app.db.repositories import SQLAlchemySubscriptionProvider
from app.db.session import create_session_factory


@pytest.mark.asyncio
async def test_database_subscription_provider_returns_enabled_profile(db_engine: Engine) -> None:
    sessions = create_session_factory(db_engine)
    with sessions.begin() as session:
        session.add(
            User(
                id="user-1",
                identity="Agent engineering candidate",
                email="candidate@example.com",
                timezone="Asia/Shanghai",
            )
        )
        session.add(
            Subscription(
                user_id="user-1",
                topics=["agents"],
                keywords=["tool calling"],
                excluded_keywords=["crypto"],
                delivery_time=time(9, 0),
                enabled=True,
            )
        )

    profile = await SQLAlchemySubscriptionProvider(sessions).get("user-1")

    assert profile is not None
    assert profile.identity == "Agent engineering candidate"
    assert profile.topics == ["agents"]
    assert profile.timezone == "Asia/Shanghai"


@pytest.mark.asyncio
async def test_database_subscription_provider_hides_disabled_subscription(
    db_engine: Engine,
) -> None:
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
        session.add(Subscription(user_id="user-1", enabled=False))

    assert await SQLAlchemySubscriptionProvider(sessions).get("user-1") is None
