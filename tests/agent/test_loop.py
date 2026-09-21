import asyncio
import json

import pytest
from pydantic import BaseModel

from app.agent.errors import AgentBudgetExceeded, AgentProtocolError
from app.agent.fake import ScriptedModelClient
from app.agent.loop import AgentBudgets, AgentLoop
from app.agent.types import ModelResponse, ModelUsage, ToolCall, TraceEventType
from app.tools.registry import ToolRegistry


class RecordArguments(BaseModel):
    value: str


class NoArguments(BaseModel):
    pass


def make_recording_registry(recorded: list[str]) -> ToolRegistry:
    registry = ToolRegistry()

    def record(arguments: RecordArguments) -> dict[str, str]:
        recorded.append(arguments.value)
        return {"recorded": arguments.value}

    registry.register(
        name="record",
        description="Record one value for the test.",
        arguments_model=RecordArguments,
        handler=record,
    )
    return registry


def make_order_registry(recorded: list[str]) -> ToolRegistry:
    registry = ToolRegistry()

    def register_named_tool(name: str) -> None:
        def handler(arguments: NoArguments) -> dict[str, str]:
            recorded.append(name)
            return {"called": name}

        registry.register(
            name=name,
            description=f"Run the {name} test step.",
            arguments_model=NoArguments,
            handler=handler,
        )

    register_named_tool("search")
    register_named_tool("write")
    return registry


def tool_response(call_id: str, value: str) -> ModelResponse:
    return ModelResponse(
        tool_calls=(ToolCall(id=call_id, name="record", arguments={"value": value}),),
        usage=ModelUsage(input_tokens=10, output_tokens=2),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("requested_order", "final_output"),
    [
        (("search", "write"), "searched, then wrote"),
        (("write", "search"), "wrote, then searched"),
    ],
)
async def test_model_controls_tool_order_without_loop_changes(
    requested_order: tuple[str, str],
    final_output: str,
) -> None:
    recorded: list[str] = []
    model = ScriptedModelClient(
        [
            ModelResponse(
                tool_calls=(ToolCall(id="call-1", name=requested_order[0], arguments={}),)
            ),
            ModelResponse(
                tool_calls=(ToolCall(id="call-2", name=requested_order[1], arguments={}),)
            ),
            ModelResponse(
                content=final_output,
                usage=ModelUsage(input_tokens=5, output_tokens=3),
            ),
        ]
    )
    loop = AgentLoop(model=model, tools=make_order_registry(recorded))

    result = await loop.run(goal="Complete the scripted task", system_prompt="Use tools")

    assert recorded == list(requested_order)
    assert result.final_output == final_output
    assert result.turns == 3
    assert result.tool_calls == 2
    assert result.usage.input_tokens == 5
    assert result.usage.output_tokens == 3
    assert [event.sequence for event in result.trace] == list(range(1, len(result.trace) + 1))
    assert result.trace[-1].event_type is TraceEventType.RUN_COMPLETED

    second_request_messages = model.requests[1][0]
    observation = json.loads(second_request_messages[-1].content or "{}")
    assert second_request_messages[-1].role == "tool"
    assert observation == {"ok": True, "result": {"called": requested_order[0]}}


@pytest.mark.asyncio
async def test_tool_error_is_returned_to_model_for_recovery() -> None:
    model = ScriptedModelClient(
        [
            ModelResponse(
                tool_calls=(ToolCall(id="bad-call", name="not_registered", arguments={}),)
            ),
            ModelResponse(content="Recovered after observing the tool error."),
        ]
    )
    loop = AgentLoop(model=model, tools=ToolRegistry())

    result = await loop.run(goal="Try a tool", system_prompt="Recover from errors")

    observation = json.loads(model.requests[1][0][-1].content or "{}")
    assert observation["ok"] is False
    assert observation["error"]["code"] == "unknown_tool"
    assert result.final_output.startswith("Recovered")


@pytest.mark.asyncio
async def test_empty_model_response_fails_with_protocol_error() -> None:
    loop = AgentLoop(
        model=ScriptedModelClient([ModelResponse()]),
        tools=ToolRegistry(),
    )

    with pytest.raises(AgentProtocolError) as error:
        await loop.run(goal="Do something", system_prompt="Be useful")

    assert error.value.code == "empty_model_response"
    assert error.value.trace[-1].event_type is TraceEventType.RUN_FAILED


@pytest.mark.asyncio
async def test_turn_budget_fails_clearly() -> None:
    recorded: list[str] = []
    loop = AgentLoop(
        model=ScriptedModelClient([tool_response("call-1", "one"), tool_response("call-2", "two")]),
        tools=make_recording_registry(recorded),
        budgets=AgentBudgets(max_turns=2, max_tool_calls=5),
    )

    with pytest.raises(AgentBudgetExceeded) as error:
        await loop.run(goal="Never finish", system_prompt="Use tools forever")

    assert error.value.code == "turn_budget"
    assert error.value.turns == 2
    assert error.value.tool_calls == 2
    assert recorded == ["one", "two"]


@pytest.mark.asyncio
async def test_tool_call_budget_stops_before_extra_execution() -> None:
    recorded: list[str] = []
    model = ScriptedModelClient(
        [
            ModelResponse(
                tool_calls=(
                    ToolCall(id="call-1", name="record", arguments={"value": "one"}),
                    ToolCall(id="call-2", name="record", arguments={"value": "two"}),
                )
            )
        ]
    )
    loop = AgentLoop(
        model=model,
        tools=make_recording_registry(recorded),
        budgets=AgentBudgets(max_tool_calls=1),
    )

    with pytest.raises(AgentBudgetExceeded) as error:
        await loop.run(goal="Call twice", system_prompt="Use tools")

    assert error.value.code == "tool_call_budget"
    assert recorded == ["one"]


@pytest.mark.asyncio
async def test_wall_clock_budget_cancels_slow_model() -> None:
    class SlowModel:
        async def complete(self, messages: object, tools: object) -> ModelResponse:
            await asyncio.sleep(0.05)
            return ModelResponse(content="Too late")

    loop = AgentLoop(
        model=SlowModel(),  # type: ignore[arg-type]
        tools=ToolRegistry(),
        budgets=AgentBudgets(run_timeout_seconds=0.001),
    )

    with pytest.raises(AgentBudgetExceeded) as error:
        await loop.run(goal="Wait", system_prompt="Be slow")

    assert error.value.code == "run_timeout"
