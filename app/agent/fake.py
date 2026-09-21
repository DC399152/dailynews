from __future__ import annotations

from collections.abc import Sequence

from app.agent.types import AgentMessage, ModelResponse, ToolDefinition


class ScriptedModelClient:
    """Deterministic model double used by tests and credential-free demos."""

    def __init__(self, responses: Sequence[ModelResponse]) -> None:
        self._responses = tuple(responses)
        self.requests: list[tuple[tuple[AgentMessage, ...], tuple[ToolDefinition, ...]]] = []

    async def complete(
        self,
        messages: Sequence[AgentMessage],
        tools: Sequence[ToolDefinition],
    ) -> ModelResponse:
        self.requests.append((tuple(messages), tuple(tools)))
        response_index = len(self.requests) - 1
        if response_index >= len(self._responses):
            raise AssertionError("ScriptedModelClient has no response left")
        return self._responses[response_index]
