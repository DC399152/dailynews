from __future__ import annotations

import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ToolCall(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class AgentMessage(BaseModel):
    model_config = ConfigDict(frozen=True)

    role: Literal["system", "user", "assistant", "tool"]
    content: str | None = None
    tool_call_id: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()


class ModelUsage(BaseModel):
    model_config = ConfigDict(frozen=True)

    input_tokens: int = 0
    output_tokens: int = 0


class ModelResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    content: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()
    usage: ModelUsage = Field(default_factory=ModelUsage)


class ToolDefinition(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    description: str
    parameters: dict[str, Any]


class ToolExecution(BaseModel):
    model_config = ConfigDict(frozen=True)

    call_id: str
    name: str
    success: bool
    output: Any = None
    error_code: str | None = None
    error_message: str | None = None
    duration_ms: float = 0

    def observation(self) -> str:
        payload: dict[str, Any] = {"ok": self.success}
        if self.success:
            payload["result"] = self.output
        else:
            payload["error"] = {
                "code": self.error_code,
                "message": self.error_message,
            }
        return json.dumps(payload, ensure_ascii=False, default=str)


class TraceEventType(StrEnum):
    RUN_STARTED = "run_started"
    MODEL_REQUESTED = "model_requested"
    MODEL_RESPONDED = "model_responded"
    TOOL_STARTED = "tool_started"
    TOOL_COMPLETED = "tool_completed"
    RUN_COMPLETED = "run_completed"
    RUN_FAILED = "run_failed"


class TraceEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    sequence: int
    event_type: TraceEventType
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    turn: int | None = None
    tool_call_id: str | None = None
    tool_name: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class AgentRunResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str
    final_output: str
    turns: int
    tool_calls: int
    usage: ModelUsage
    trace: tuple[TraceEvent, ...]
