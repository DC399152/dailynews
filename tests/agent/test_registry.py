import asyncio
import json

import pytest
from pydantic import BaseModel, Field

from app.agent.types import ToolCall
from app.tools.registry import ToolRegistry


class EchoArguments(BaseModel):
    value: str = Field(min_length=1)


def make_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        name="echo",
        description="Return the supplied value.",
        arguments_model=EchoArguments,
        handler=lambda arguments: {"echo": arguments.value},
    )
    return registry


@pytest.mark.asyncio
async def test_registry_exposes_json_schema_and_executes_validated_handler() -> None:
    registry = make_registry()

    definitions = registry.definitions()
    execution = await registry.execute(
        ToolCall(id="call-1", name="echo", arguments={"value": "hello"}),
        timeout_seconds=1,
    )

    assert definitions[0].name == "echo"
    assert definitions[0].parameters["required"] == ["value"]
    assert execution.success is True
    assert execution.output == {"echo": "hello"}
    assert json.loads(execution.observation()) == {
        "ok": True,
        "result": {"echo": "hello"},
    }


@pytest.mark.asyncio
async def test_registry_returns_validation_error_as_tool_observation() -> None:
    execution = await make_registry().execute(
        ToolCall(id="call-1", name="echo", arguments={"value": ""}),
        timeout_seconds=1,
    )

    assert execution.success is False
    assert execution.error_code == "invalid_arguments"
    assert json.loads(execution.observation())["error"]["code"] == "invalid_arguments"


@pytest.mark.asyncio
async def test_registry_reports_unknown_tool_without_crashing_agent() -> None:
    execution = await make_registry().execute(
        ToolCall(id="call-1", name="missing", arguments={}),
        timeout_seconds=1,
    )

    assert execution.success is False
    assert execution.error_code == "unknown_tool"


@pytest.mark.asyncio
async def test_registry_enforces_per_tool_timeout() -> None:
    async def slow_handler(arguments: EchoArguments) -> str:
        await asyncio.sleep(0.05)
        return arguments.value

    registry = ToolRegistry()
    registry.register(
        name="slow",
        description="A deliberately slow tool.",
        arguments_model=EchoArguments,
        handler=slow_handler,
    )

    execution = await registry.execute(
        ToolCall(id="call-1", name="slow", arguments={"value": "hello"}),
        timeout_seconds=0.001,
    )

    assert execution.success is False
    assert execution.error_code == "tool_timeout"
