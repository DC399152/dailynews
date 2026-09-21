from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, Field

from app.tools.errors import ToolFailure


class SubscriptionProfile(BaseModel):
    user_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    identity: str = Field(min_length=1, max_length=1_000)
    topics: list[str] = Field(default_factory=list, max_length=50)
    keywords: list[str] = Field(default_factory=list, max_length=100)
    excluded_keywords: list[str] = Field(default_factory=list, max_length=100)
    email: str = Field(min_length=3, max_length=320)
    timezone: str = Field(default="UTC", min_length=1, max_length=100)


class GetSubscriptionArguments(BaseModel):
    user_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")


class SubscriptionProvider(Protocol):
    async def get(self, user_id: str) -> SubscriptionProfile | None: ...


class InMemorySubscriptionProvider:
    def __init__(self, profiles: list[SubscriptionProfile] | None = None) -> None:
        self._profiles = {profile.user_id: profile for profile in profiles or ()}

    async def get(self, user_id: str) -> SubscriptionProfile | None:
        return self._profiles.get(user_id)

    def put(self, profile: SubscriptionProfile) -> None:
        self._profiles[profile.user_id] = profile


class SubscriptionTool:
    def __init__(self, provider: SubscriptionProvider) -> None:
        self._provider = provider

    async def get_subscription(self, arguments: GetSubscriptionArguments) -> dict[str, object]:
        profile = await self._provider.get(arguments.user_id)
        if profile is None:
            raise ToolFailure(
                "subscription_not_found",
                f"No subscription exists for user: {arguments.user_id}",
            )
        return profile.model_dump(mode="json")
