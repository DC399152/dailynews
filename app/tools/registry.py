from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError

from app.agent.types import ToolCall, ToolDefinition, ToolExecution
from app.tools.errors import ToolFailure

ToolHandler = Callable[[BaseModel], Any | Coroutine[Any, Any, Any]]


@dataclass(frozen=True, slots=True)
class RegisteredTool:
    name: str
    description: str
    arguments_model: type[BaseModel]
    handler: ToolHandler

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=self.arguments_model.model_json_schema(),
        )


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, RegisteredTool] = {}

    def register(
        self,
        *,
        name: str,
        description: str,
        arguments_model: type[BaseModel],
        handler: ToolHandler,
    ) -> None:
        if name in self._tools:
            raise ValueError(f"Tool is already registered: {name}")
        self._tools[name] = RegisteredTool(
            name=name,
            description=description,
            arguments_model=arguments_model,
            handler=handler,
        )

    def definitions(self) -> tuple[ToolDefinition, ...]:
        return tuple(tool.definition() for tool in self._tools.values())

    async def execute(self, call: ToolCall, *, timeout_seconds: float) -> ToolExecution:
        started = time.perf_counter()
        tool = self._tools.get(call.name)
        if tool is None:
            return self._failure(
                call,
                started,
                code="unknown_tool",
                message=f"Unknown tool: {call.name}",
            )

        try:
            arguments = tool.arguments_model.model_validate(call.arguments)
        except ValidationError as exc:
            return self._failure(
                call,
                started,
                code="invalid_arguments",
                message=str(exc),
            )

        try:
            async with asyncio.timeout(timeout_seconds):
                output = await self._invoke(tool.handler, arguments)
        except TimeoutError:
            return self._failure(
                call,
                started,
                code="tool_timeout",
                message=f"Tool exceeded {timeout_seconds:g} seconds",
            )
        except ToolFailure as exc:
            return self._failure(
                call,
                started,
                code=exc.code,
                message=str(exc),
            )
        except Exception as exc:  # noqa: BLE001 - tool failures become model observations
            return self._failure(
                call,
                started,
                code="tool_error",
                message=f"{type(exc).__name__}: {exc}",
            )

        if isinstance(output, BaseModel):
            output = output.model_dump(mode="json")
        return ToolExecution(
            call_id=call.id,
            name=call.name,
            success=True,
            output=output,
            duration_ms=self._duration_ms(started),
        )

    @staticmethod
    async def _invoke(handler: ToolHandler, arguments: BaseModel) -> Any:
        if inspect.iscoroutinefunction(handler):
            return await handler(arguments)

        result = await asyncio.to_thread(handler, arguments)
        if inspect.isawaitable(result):
            return await result
        return result

    @staticmethod
    def _failure(
        call: ToolCall,
        started: float,
        *,
        code: str,
        message: str,
    ) -> ToolExecution:
        return ToolExecution(
            call_id=call.id,
            name=call.name,
            success=False,
            error_code=code,
            error_message=message,
            duration_ms=ToolRegistry._duration_ms(started),
        )

    @staticmethod
    def _duration_ms(started: float) -> float:
        return round((time.perf_counter() - started) * 1000, 3)
