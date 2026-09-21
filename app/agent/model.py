from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any, Protocol

from openai import AsyncOpenAI

from app.agent.errors import ModelClientError
from app.agent.types import (
    AgentMessage,
    ModelResponse,
    ModelUsage,
    ToolCall,
    ToolDefinition,
)


class ModelClient(Protocol):
    async def complete(
        self,
        messages: Sequence[AgentMessage],
        tools: Sequence[ToolDefinition],
    ) -> ModelResponse: ...


class OpenAICompatibleModelClient:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        client: AsyncOpenAI | None = None,
    ) -> None:
        if not model:
            raise ValueError("LLM_MODEL must be configured")
        if client is None and not api_key:
            raise ValueError("LLM_API_KEY must be configured")
        self._model = model
        self._client = client or AsyncOpenAI(api_key=api_key, base_url=base_url)

    async def complete(
        self,
        messages: Sequence[AgentMessage],
        tools: Sequence[ToolDefinition],
    ) -> ModelResponse:
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[self._message_payload(message) for message in messages],  # type: ignore[arg-type]
            tools=[self._tool_payload(tool) for tool in tools],  # type: ignore[arg-type]
            tool_choice="auto",
        )
        if not response.choices:
            raise ModelClientError("Model provider returned no choices")

        message = response.choices[0].message
        tool_calls: list[ToolCall] = []
        for raw_call in message.tool_calls or ():
            try:
                arguments = json.loads(raw_call.function.arguments)
            except json.JSONDecodeError as exc:
                raise ModelClientError(
                    f"Model returned invalid JSON for tool {raw_call.function.name}"
                ) from exc
            if not isinstance(arguments, dict):
                raise ModelClientError(
                    f"Tool arguments must be an object: {raw_call.function.name}"
                )
            tool_calls.append(
                ToolCall(
                    id=raw_call.id,
                    name=raw_call.function.name,
                    arguments=arguments,
                )
            )

        usage = response.usage
        return ModelResponse(
            content=message.content,
            tool_calls=tuple(tool_calls),
            usage=ModelUsage(
                input_tokens=usage.prompt_tokens if usage else 0,
                output_tokens=usage.completion_tokens if usage else 0,
            ),
        )

    @staticmethod
    def _message_payload(message: AgentMessage) -> dict[str, Any]:
        payload: dict[str, Any] = {"role": message.role, "content": message.content}
        if message.tool_call_id:
            payload["tool_call_id"] = message.tool_call_id
        if message.tool_calls:
            payload["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": json.dumps(call.arguments, ensure_ascii=False),
                    },
                }
                for call in message.tool_calls
            ]
        return payload

    @staticmethod
    def _tool_payload(tool: ToolDefinition) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            },
        }
