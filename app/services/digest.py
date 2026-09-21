from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete

from app.agent.errors import AgentRunError
from app.agent.loop import AgentBudgets, AgentLoop
from app.agent.model import ModelClient
from app.agent.types import AgentRunResult, TraceEvent, TraceEventType
from app.db.models import (
    AgentRun,
    Digest,
    DigestStatus,
    RunStatus,
    ToolCallRecord,
)
from app.db.repositories import SQLAlchemySubscriptionProvider
from app.db.session import SessionFactory
from app.services.prompts import DIGEST_SYSTEM_PROMPT, build_digest_goal
from app.settings import Settings
from app.tools.defaults import build_default_tool_registry
from app.tools.registry import ToolRegistry
from app.tools.subscription import SubscriptionProvider

ModelClientFactory = Callable[[], ModelClient]
ToolRegistryFactory = Callable[[Settings, SubscriptionProvider], ToolRegistry]


def default_tool_registry_factory(
    settings: Settings,
    subscriptions: SubscriptionProvider,
) -> ToolRegistry:
    return build_default_tool_registry(settings, subscriptions=subscriptions)


class DigestService:
    def __init__(
        self,
        *,
        settings: Settings,
        sessions: SessionFactory,
        model_factory: ModelClientFactory,
        tool_registry_factory: ToolRegistryFactory | None = None,
    ) -> None:
        self._settings = settings
        self._sessions = sessions
        self._model_factory = model_factory
        self._tool_registry_factory = tool_registry_factory or default_tool_registry_factory

    @property
    def model_name(self) -> str:
        return self._settings.llm_model or "unconfigured"

    async def execute_run(self, run_id: str) -> None:
        user_id = self._mark_running(run_id)
        if user_id is None:
            return

        try:
            provider = SQLAlchemySubscriptionProvider(self._sessions)
            tools = self._tool_registry_factory(self._settings, provider)
            loop = AgentLoop(
                model=self._model_factory(),
                tools=tools,
                budgets=AgentBudgets(
                    max_turns=self._settings.agent_max_turns,
                    max_tool_calls=self._settings.agent_max_tool_calls,
                    run_timeout_seconds=self._settings.agent_run_timeout_seconds,
                    tool_timeout_seconds=self._settings.tool_timeout_seconds,
                ),
            )
            result = await loop.run(
                goal=build_digest_goal(user_id, run_id),
                system_prompt=DIGEST_SYSTEM_PROMPT,
            )
            self._complete_run(run_id, user_id, result)
        except AgentRunError as exc:
            self._fail_run(
                run_id,
                code=exc.code,
                message=str(exc),
                turns=exc.turns,
                tool_calls=exc.tool_calls,
                trace=exc.trace,
            )
        except Exception as exc:  # noqa: BLE001 - background task must reach terminal state
            self._fail_run(
                run_id,
                code="execution_error",
                message=f"{type(exc).__name__}: {exc}",
            )

    def _mark_running(self, run_id: str) -> str | None:
        with self._sessions() as session, session.begin():
            run = session.get(AgentRun, run_id)
            if run is None or run.status != RunStatus.PENDING:
                return None
            run.status = RunStatus.RUNNING
            run.started_at = datetime.now(UTC)
            return run.user_id

    def _complete_run(self, run_id: str, user_id: str, result: AgentRunResult) -> None:
        try:
            with self._sessions() as session, session.begin():
                run = session.get(AgentRun, run_id)
                if run is None:
                    return
                self._replace_tool_calls(session, run_id, result.trace)
                digest_data = self._digest_from_trace(result.final_output, result.trace)
                session.add(
                    Digest(
                        user_id=user_id,
                        run_id=run_id,
                        title=digest_data["title"],
                        content=digest_data["content"],
                        sources=digest_data["sources"],
                        status=digest_data["status"],
                        delivered_at=digest_data["delivered_at"],
                    )
                )
                run.status = RunStatus.COMPLETED
                run.turn_count = result.turns
                run.tool_call_count = result.tool_calls
                run.input_tokens = result.usage.input_tokens
                run.output_tokens = result.usage.output_tokens
                run.finished_at = datetime.now(UTC)
        except Exception as exc:
            self._fail_run(
                run_id,
                code="persistence_error",
                message=f"Could not persist completed run: {type(exc).__name__}: {exc}",
                turns=result.turns,
                tool_calls=result.tool_calls,
                trace=result.trace,
            )

    def _fail_run(
        self,
        run_id: str,
        *,
        code: str,
        message: str,
        turns: int = 0,
        tool_calls: int = 0,
        trace: Sequence[TraceEvent] = (),
    ) -> None:
        with self._sessions() as session, session.begin():
            run = session.get(AgentRun, run_id)
            if run is None:
                return
            self._replace_tool_calls(session, run_id, trace)
            run.status = RunStatus.FAILED
            run.error_code = code[:100]
            run.error_message = message[:10_000]
            run.turn_count = turns
            run.tool_call_count = tool_calls
            run.finished_at = datetime.now(UTC)

    @staticmethod
    def _replace_tool_calls(
        session: Any,
        run_id: str,
        trace: Sequence[TraceEvent],
    ) -> None:
        session.execute(delete(ToolCallRecord).where(ToolCallRecord.run_id == run_id))
        started: dict[str, tuple[int, TraceEvent]] = {}
        sequence = 0
        for event in trace:
            if event.event_type is TraceEventType.TOOL_STARTED and event.tool_call_id:
                sequence += 1
                started[event.tool_call_id] = (sequence, event)
            elif event.event_type is TraceEventType.TOOL_COMPLETED and event.tool_call_id:
                start_data = started.pop(event.tool_call_id, None)
                if start_data is None:
                    continue
                call_sequence, start = start_data
                session.add(
                    ToolCallRecord(
                        run_id=run_id,
                        sequence=call_sequence,
                        turn=start.turn or 0,
                        call_id=event.tool_call_id,
                        tool_name=event.tool_name or start.tool_name or "unknown",
                        arguments=DigestService._json_value(start.data.get("arguments", {})),
                        success=bool(event.data.get("success")),
                        result_preview=DigestService._preview(event.data.get("output")),
                        error_code=DigestService._optional_text(event.data.get("error_code"), 100),
                        error_message=DigestService._optional_text(
                            event.data.get("error_message"), 4_000
                        ),
                        duration_ms=float(event.data.get("duration_ms") or 0),
                    )
                )

        for call_sequence, start in started.values():
            session.add(
                ToolCallRecord(
                    run_id=run_id,
                    sequence=call_sequence,
                    turn=start.turn or 0,
                    call_id=start.tool_call_id or "unknown",
                    tool_name=start.tool_name or "unknown",
                    arguments=DigestService._json_value(start.data.get("arguments", {})),
                    success=False,
                    error_code="incomplete_tool_call",
                    error_message="Run ended before this tool call completed",
                    duration_ms=0,
                )
            )

    @staticmethod
    def _digest_from_trace(final_output: str, trace: Sequence[TraceEvent]) -> dict[str, Any]:
        title = "Daily AI Brief"
        content = final_output
        status = DigestStatus.GENERATED
        delivered_at: datetime | None = None
        sources: list[dict[str, Any]] = []
        seen_urls: set[str] = set()

        for event in trace:
            if event.event_type is TraceEventType.TOOL_STARTED:
                arguments = event.data.get("arguments", {})
                if not isinstance(arguments, dict):
                    continue
                if event.tool_name == "send_digest":
                    title = str(arguments.get("subject") or title)[:300]
                    content = str(arguments.get("content") or content)
                elif event.tool_name == "write_file" and arguments.get("content"):
                    content = str(arguments["content"])
                elif event.tool_name == "fetch_article" and arguments.get("url"):
                    DigestService._append_source(
                        sources,
                        seen_urls,
                        {"url": str(arguments["url"])},
                    )
            elif event.event_type is TraceEventType.TOOL_COMPLETED and event.data.get("success"):
                output = event.data.get("output")
                if event.tool_name == "search_news" and isinstance(output, dict):
                    items = output.get("items", [])
                    if isinstance(items, list):
                        for item in items:
                            if isinstance(item, dict) and item.get("url"):
                                DigestService._append_source(sources, seen_urls, item)
                elif event.tool_name == "send_digest" and isinstance(output, dict):
                    if output.get("mode") == "smtp" and output.get("delivered") is True:
                        status = DigestStatus.DELIVERED
                        delivered_at = datetime.now(UTC)
                    elif output.get("mode") == "outbox":
                        status = DigestStatus.OUTBOX

        return {
            "title": title,
            "content": content,
            "sources": sources,
            "status": status,
            "delivered_at": delivered_at,
        }

    @staticmethod
    def _append_source(
        sources: list[dict[str, Any]],
        seen_urls: set[str],
        source: dict[str, Any],
    ) -> None:
        url = str(source.get("url", ""))
        if not url or url in seen_urls:
            return
        seen_urls.add(url)
        sources.append(
            {
                "url": url,
                "title": str(source.get("title", ""))[:500],
                "source": str(source.get("source", ""))[:200],
                "published_at": source.get("published_at"),
            }
        )

    @staticmethod
    def _preview(value: Any) -> str | None:
        if value is None:
            return None
        return json.dumps(value, ensure_ascii=False, default=str)[:4_000]

    @staticmethod
    def _json_value(value: Any) -> Any:
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))

    @staticmethod
    def _optional_text(value: Any, limit: int) -> str | None:
        return str(value)[:limit] if value is not None else None
