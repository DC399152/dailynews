import json
from types import SimpleNamespace
from typing import Any

import pytest

from app.agent.errors import ModelClientError
from app.agent.model import OpenAICompatibleModelClient
from app.agent.types import AgentMessage, ToolCall, ToolDefinition


class FakeCompletions:
    def __init__(self, response: Any) -> None:
        self.response = response
        self.request: dict[str, Any] | None = None

    async def create(self, **kwargs: Any) -> Any:
        self.request = kwargs
        return self.response


class FakeOpenAIClient:
    def __init__(self, response: Any) -> None:
        self.chat = SimpleNamespace(completions=FakeCompletions(response))


def provider_response(*, arguments: str = '{"query": "agents"}') -> Any:
    message = SimpleNamespace(
        content=None,
        tool_calls=(
            SimpleNamespace(
                id="call-1",
                function=SimpleNamespace(name="search_news", arguments=arguments),
            ),
        ),
    )
    return SimpleNamespace(
        choices=(SimpleNamespace(message=message),),
        usage=SimpleNamespace(prompt_tokens=11, completion_tokens=4),
    )


@pytest.mark.asyncio
async def test_openai_adapter_translates_messages_tools_and_response() -> None:
    fake_client = FakeOpenAIClient(provider_response())
    client = OpenAICompatibleModelClient(
        api_key="",
        base_url="http://unused",
        model="test-model",
        client=fake_client,  # type: ignore[arg-type]
    )
    messages = (
        AgentMessage(role="user", content="Find recent news"),
        AgentMessage(
            role="assistant",
            tool_calls=(ToolCall(id="previous", name="search_news", arguments={"query": "AI"}),),
        ),
        AgentMessage(role="tool", tool_call_id="previous", content='{"ok": true}'),
    )
    tools = (
        ToolDefinition(
            name="search_news",
            description="Search news",
            parameters={"type": "object", "properties": {"query": {"type": "string"}}},
        ),
    )

    result = await client.complete(messages, tools)

    assert result.tool_calls[0].arguments == {"query": "agents"}
    assert result.usage.input_tokens == 11
    assert result.usage.output_tokens == 4
    request = fake_client.chat.completions.request
    assert request is not None
    assert request["model"] == "test-model"
    assert request["tools"][0]["function"]["name"] == "search_news"
    assert json.loads(request["messages"][1]["tool_calls"][0]["function"]["arguments"]) == {
        "query": "AI"
    }
    assert request["messages"][2]["tool_call_id"] == "previous"


@pytest.mark.asyncio
async def test_openai_adapter_rejects_non_json_tool_arguments() -> None:
    client = OpenAICompatibleModelClient(
        api_key="",
        base_url="http://unused",
        model="test-model",
        client=FakeOpenAIClient(provider_response(arguments="not-json")),  # type: ignore[arg-type]
    )

    with pytest.raises(ModelClientError, match="invalid JSON"):
        await client.complete((), ())
