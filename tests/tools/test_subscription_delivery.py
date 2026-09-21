import json
from pathlib import Path

import pytest

from app.tools.delivery import DigestDeliveryTool, SendDigestArguments
from app.tools.errors import ToolFailure, ToolPolicyViolation
from app.tools.subscription import (
    GetSubscriptionArguments,
    InMemorySubscriptionProvider,
    SubscriptionProfile,
    SubscriptionTool,
)


def profile(email: str = "developer@example.com") -> SubscriptionProfile:
    return SubscriptionProfile(
        user_id="user-1",
        identity="AI agent intern candidate",
        topics=["agents", "AI coding"],
        keywords=["tool calling"],
        excluded_keywords=["cryptocurrency"],
        email=email,
        timezone="Asia/Shanghai",
    )


@pytest.mark.asyncio
async def test_subscription_tool_returns_preferences() -> None:
    provider = InMemorySubscriptionProvider([profile()])
    tool = SubscriptionTool(provider)

    result = await tool.get_subscription(GetSubscriptionArguments(user_id="user-1"))

    assert result["identity"] == "AI agent intern candidate"
    assert result["topics"] == ["agents", "AI coding"]


@pytest.mark.asyncio
async def test_subscription_tool_reports_missing_user() -> None:
    tool = SubscriptionTool(InMemorySubscriptionProvider())

    with pytest.raises(ToolFailure) as error:
        await tool.get_subscription(GetSubscriptionArguments(user_id="missing"))

    assert error.value.code == "subscription_not_found"


@pytest.mark.asyncio
async def test_delivery_writes_credential_free_development_outbox(tmp_path: Path) -> None:
    provider = InMemorySubscriptionProvider([profile()])
    tool = DigestDeliveryTool(subscriptions=provider, outbox_dir=tmp_path / "outbox")

    result = await tool.send_digest(
        SendDigestArguments(
            user_id="user-1",
            subject="Daily AI Brief",
            content="One important agent release.",
        )
    )

    outbox_path = tmp_path / str(result["path"])
    payload = json.loads(outbox_path.read_text(encoding="utf-8"))
    assert result["mode"] == "outbox"
    assert result["delivered"] is False
    assert payload["recipient"] == "developer@example.com"
    assert payload["content"] == "One important agent release."


@pytest.mark.asyncio
async def test_delivery_rejects_header_injection_email(tmp_path: Path) -> None:
    provider = InMemorySubscriptionProvider([profile("good@example.com\nBcc: bad@example.com")])
    tool = DigestDeliveryTool(subscriptions=provider, outbox_dir=tmp_path / "outbox")

    with pytest.raises(ToolPolicyViolation) as error:
        await tool.send_digest(
            SendDigestArguments(user_id="user-1", subject="Brief", content="Content")
        )

    assert error.value.code == "invalid_email"


@pytest.mark.asyncio
async def test_delivery_rejects_header_injection_subject(tmp_path: Path) -> None:
    provider = InMemorySubscriptionProvider([profile()])
    tool = DigestDeliveryTool(subscriptions=provider, outbox_dir=tmp_path / "outbox")

    with pytest.raises(ToolPolicyViolation) as error:
        await tool.send_digest(
            SendDigestArguments(
                user_id="user-1",
                subject="Brief\nBcc: bad@example.com",
                content="Content",
            )
        )

    assert error.value.code == "invalid_subject"
