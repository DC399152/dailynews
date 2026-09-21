from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from app.agent.errors import AgentBudgetExceeded, AgentProtocolError, AgentRunError
from app.agent.model import ModelClient
from app.agent.types import (
    AgentMessage,
    AgentRunResult,
    ModelUsage,
    TraceEvent,
    TraceEventType,
)
from app.tools.registry import ToolRegistry


@dataclass(frozen=True, slots=True)
class AgentBudgets:
    max_turns: int = 12
    max_tool_calls: int = 24
    run_timeout_seconds: float = 180
    tool_timeout_seconds: float = 15

    def __post_init__(self) -> None:
        for name, value in (
            ("max_turns", self.max_turns),
            ("max_tool_calls", self.max_tool_calls),
            ("run_timeout_seconds", self.run_timeout_seconds),
            ("tool_timeout_seconds", self.tool_timeout_seconds),
        ):
            if value <= 0:
                raise ValueError(f"{name} must be greater than zero")


class AgentLoop:
    def __init__(
        self,
        *,
        model: ModelClient,
        tools: ToolRegistry,
        budgets: AgentBudgets | None = None,
    ) -> None:
        self._model = model
        self._tools = tools
        self._budgets = budgets or AgentBudgets()

    async def run(self, *, goal: str, system_prompt: str) -> AgentRunResult:
        run_id = str(uuid4())
        trace: list[TraceEvent] = []
        messages = [
            AgentMessage(role="system", content=system_prompt),
            AgentMessage(role="user", content=goal),
        ]
        counters = {"turns": 0, "tool_calls": 0, "input_tokens": 0, "output_tokens": 0}
        self._trace(trace, TraceEventType.RUN_STARTED, data={"run_id": run_id})

        try:
            async with asyncio.timeout(self._budgets.run_timeout_seconds):
                return await self._run(run_id, messages, trace, counters)
        except TimeoutError as exc:
            error = self._budget_error(
                "run_timeout",
                f"Run exceeded {self._budgets.run_timeout_seconds:g} seconds",
                trace,
                counters,
            )
            raise error from exc
        except AgentRunError:
            raise
        except Exception as exc:
            self._trace(
                trace,
                TraceEventType.RUN_FAILED,
                data={"code": "execution_error", "message": f"{type(exc).__name__}: {exc}"},
            )
            raise AgentRunError(
                f"Agent run failed: {type(exc).__name__}: {exc}",
                code="execution_error",
                trace=trace,
                turns=counters["turns"],
                tool_calls=counters["tool_calls"],
            ) from exc

    async def _run(
        self,
        run_id: str,
        messages: list[AgentMessage],
        trace: list[TraceEvent],
        counters: dict[str, int],
    ) -> AgentRunResult:
        for turn in range(1, self._budgets.max_turns + 1):
            counters["turns"] = turn
            self._trace(trace, TraceEventType.MODEL_REQUESTED, turn=turn)
            response = await self._model.complete(messages, self._tools.definitions())
            counters["input_tokens"] += response.usage.input_tokens
            counters["output_tokens"] += response.usage.output_tokens
            self._trace(
                trace,
                TraceEventType.MODEL_RESPONDED,
                turn=turn,
                data={
                    "tool_count": len(response.tool_calls),
                    "has_content": bool(response.content),
                },
            )
            messages.append(
                AgentMessage(
                    role="assistant",
                    content=response.content,
                    tool_calls=response.tool_calls,
                )
            )

            if not response.tool_calls:
                if not response.content or not response.content.strip():
                    self._trace(
                        trace,
                        TraceEventType.RUN_FAILED,
                        turn=turn,
                        data={"code": "empty_model_response"},
                    )
                    raise AgentProtocolError(
                        "Model returned neither tool calls nor final content",
                        code="empty_model_response",
                        trace=trace,
                        turns=counters["turns"],
                        tool_calls=counters["tool_calls"],
                    )

                self._trace(trace, TraceEventType.RUN_COMPLETED, turn=turn)
                return AgentRunResult(
                    run_id=run_id,
                    final_output=response.content,
                    turns=counters["turns"],
                    tool_calls=counters["tool_calls"],
                    usage=ModelUsage(
                        input_tokens=counters["input_tokens"],
                        output_tokens=counters["output_tokens"],
                    ),
                    trace=tuple(trace),
                )

            for call in response.tool_calls:
                if counters["tool_calls"] >= self._budgets.max_tool_calls:
                    raise self._budget_error(
                        "tool_call_budget",
                        f"Run exceeded {self._budgets.max_tool_calls} tool calls",
                        trace,
                        counters,
                    )
                counters["tool_calls"] += 1
                self._trace(
                    trace,
                    TraceEventType.TOOL_STARTED,
                    turn=turn,
                    tool_call_id=call.id,
                    tool_name=call.name,
                    data={"arguments": call.arguments},
                )
                execution = await self._tools.execute(
                    call,
                    timeout_seconds=self._budgets.tool_timeout_seconds,
                )
                self._trace(
                    trace,
                    TraceEventType.TOOL_COMPLETED,
                    turn=turn,
                    tool_call_id=call.id,
                    tool_name=call.name,
                    data={
                        "success": execution.success,
                        "duration_ms": execution.duration_ms,
                        "error_code": execution.error_code,
                        "error_message": execution.error_message,
                        "output": execution.output,
                    },
                )
                messages.append(
                    AgentMessage(
                        role="tool",
                        tool_call_id=call.id,
                        content=execution.observation(),
                    )
                )

        raise self._budget_error(
            "turn_budget",
            f"Run exceeded {self._budgets.max_turns} model turns",
            trace,
            counters,
        )

    def _budget_error(
        self,
        code: str,
        message: str,
        trace: list[TraceEvent],
        counters: dict[str, int],
    ) -> AgentBudgetExceeded:
        self._trace(trace, TraceEventType.RUN_FAILED, data={"code": code, "message": message})
        return AgentBudgetExceeded(
            message,
            code=code,
            trace=trace,
            turns=counters["turns"],
            tool_calls=counters["tool_calls"],
        )

    @staticmethod
    def _trace(
        trace: list[TraceEvent],
        event_type: TraceEventType,
        *,
        turn: int | None = None,
        tool_call_id: str | None = None,
        tool_name: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> None:
        trace.append(
            TraceEvent(
                sequence=len(trace) + 1,
                event_type=event_type,
                turn=turn,
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                data=data or {},
            )
        )
