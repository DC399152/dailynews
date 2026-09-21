from __future__ import annotations

from collections.abc import Sequence

from app.agent.types import TraceEvent


class AgentRunError(RuntimeError):
    """Base error carrying the trace accumulated before a run failed."""

    def __init__(
        self,
        message: str,
        *,
        code: str,
        trace: Sequence[TraceEvent] = (),
        turns: int = 0,
        tool_calls: int = 0,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.trace = tuple(trace)
        self.turns = turns
        self.tool_calls = tool_calls


class AgentBudgetExceeded(AgentRunError):
    """Raised when a turn, tool-call, or wall-clock budget is exhausted."""


class AgentProtocolError(AgentRunError):
    """Raised when a model response cannot advance or finish a run."""


class ModelClientError(RuntimeError):
    """Raised when a model provider returns an unusable response."""
