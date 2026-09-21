from __future__ import annotations

from datetime import datetime, time
from email.utils import parseaddr
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator


class UserCreate(BaseModel):
    user_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,64}$")
    identity: str = Field(min_length=1, max_length=1_000)
    email: str = Field(min_length=3, max_length=320)
    timezone: str = Field(default="UTC", min_length=1, max_length=100)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        display_name, address = parseaddr(value)
        if display_name or address != value or "@" not in address or "\n" in value or "\r" in value:
            raise ValueError("email must be a plain valid address")
        return value

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("timezone must be a valid IANA timezone") from exc
        return value


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    identity: str
    email: str
    timezone: str
    created_at: datetime
    updated_at: datetime


class SubscriptionUpsert(BaseModel):
    topics: list[str] = Field(default_factory=list, max_length=50)
    keywords: list[str] = Field(default_factory=list, max_length=100)
    excluded_keywords: list[str] = Field(default_factory=list, max_length=100)
    delivery_time: time = time(9, 0)
    enabled: bool = True

    @field_validator("topics", "keywords", "excluded_keywords")
    @classmethod
    def normalize_terms(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for value in values:
            term = value.strip()
            if not term:
                raise ValueError("preference terms must not be empty")
            if len(term) > 200:
                raise ValueError("preference terms must be at most 200 characters")
            key = term.casefold()
            if key not in seen:
                seen.add(key)
                normalized.append(term)
        return normalized


class SubscriptionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: str
    topics: list[str]
    keywords: list[str]
    excluded_keywords: list[str]
    delivery_time: time
    enabled: bool
    created_at: datetime
    updated_at: datetime


class AgentRunResponse(BaseModel):
    id: str
    user_id: str
    status: str
    model: str
    turn_count: int
    tool_call_count: int
    input_tokens: int
    output_tokens: int
    error_code: str | None
    error_message: str | None
    digest_id: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class ToolCallResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: str
    sequence: int
    turn: int
    call_id: str
    tool_name: str
    arguments: dict[str, Any]
    success: bool
    result_preview: str | None
    error_code: str | None
    error_message: str | None
    duration_ms: float
    created_at: datetime


class DigestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    run_id: str
    title: str
    content: str
    sources: list[dict[str, Any]]
    status: str
    created_at: datetime
    delivered_at: datetime | None
