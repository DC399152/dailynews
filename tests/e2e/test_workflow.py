import json
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import Engine

from app.agent.fake import ScriptedModelClient
from app.agent.types import ModelResponse, ToolCall
from app.main import create_app
from app.settings import Settings
from app.tools.defaults import build_default_tool_registry
from app.tools.news import SearchNewsArguments
from app.tools.subscription import SubscriptionProvider


class FakeNewsTool:
    def __init__(self) -> None:
        self.requests: list[SearchNewsArguments] = []

    async def search_news(self, arguments: SearchNewsArguments) -> dict[str, object]:
        self.requests.append(arguments)
        return {
            "query": arguments.query,
            "failed_sources": 0,
            "items": [
                {
                    "title": "A reliable agent harness release",
                    "url": "https://example.com/agent-harness",
                    "source": "Example Engineering",
                    "published_at": "2026-09-21T01:00:00+00:00",
                    "summary": "A new tool-calling runtime with trace support.",
                }
            ],
        }


def scripted_workflow() -> tuple[ModelResponse, ...]:
    digest = (
        "# Daily AI Brief\n\n"
        "## Agent engineering\n\n"
        "- [A reliable agent harness release](https://example.com/agent-harness)"
    )
    return (
        ModelResponse(
            tool_calls=(
                ToolCall(
                    id="subscription-1",
                    name="get_subscription",
                    arguments={"user_id": "candidate"},
                ),
            )
        ),
        ModelResponse(
            tool_calls=(
                ToolCall(
                    id="news-1",
                    name="search_news",
                    arguments={
                        "query": "AI agents tool calling",
                        "hours": 24,
                        "limit": 10,
                        "include_keywords": ["agents", "tool calling"],
                        "exclude_keywords": ["cryptocurrency"],
                    },
                ),
            )
        ),
        ModelResponse(
            tool_calls=(
                ToolCall(
                    id="write-1",
                    name="write_file",
                    arguments={"path": "digests/e2e.md", "content": digest},
                ),
            )
        ),
        ModelResponse(
            tool_calls=(
                ToolCall(
                    id="send-1",
                    name="send_digest",
                    arguments={
                        "user_id": "candidate",
                        "subject": "Daily AI Brief",
                        "content": digest,
                    },
                ),
            )
        ),
        ModelResponse(content="The personalized digest was saved and queued for delivery."),
    )


def test_complete_credential_free_workflow(
    test_settings: Settings,
    db_engine: Engine,
) -> None:
    fake_news = FakeNewsTool()

    def registry_factory(settings: Settings, subscriptions: SubscriptionProvider):
        return build_default_tool_registry(
            settings,
            subscriptions=subscriptions,
            news=fake_news,  # type: ignore[arg-type]
        )

    app = create_app(
        settings=test_settings,
        engine=db_engine,
        model_factory=lambda: ScriptedModelClient(scripted_workflow()),
        tool_registry_factory=registry_factory,
    )

    with TestClient(app) as client:
        assert (
            client.post(
                "/api/users",
                json={
                    "user_id": "candidate",
                    "identity": "AI agent engineering candidate",
                    "email": "candidate@example.com",
                    "timezone": "Asia/Shanghai",
                },
            ).status_code
            == 201
        )
        assert (
            client.put(
                "/api/users/candidate/subscription",
                json={
                    "topics": ["AI agents"],
                    "keywords": ["tool calling"],
                    "excluded_keywords": ["cryptocurrency"],
                    "delivery_time": "09:30:00",
                    "enabled": True,
                },
            ).status_code
            == 200
        )

        started = client.post("/api/users/candidate/digest-runs")
        assert started.status_code == 202
        run_id = started.json()["id"]

        run = client.get(f"/api/runs/{run_id}").json()
        calls = client.get(f"/api/runs/{run_id}/tool-calls").json()
        digests = client.get("/api/users/candidate/digests").json()

    assert run["status"] == "completed"
    assert run["turn_count"] == 5
    assert run["tool_call_count"] == 4
    assert [call["tool_name"] for call in calls] == [
        "get_subscription",
        "search_news",
        "write_file",
        "send_digest",
    ]
    assert all(call["success"] for call in calls)
    assert len(fake_news.requests) == 1
    assert fake_news.requests[0].include_keywords == ["agents", "tool calling"]
    assert fake_news.requests[0].exclude_keywords == ["cryptocurrency"]

    assert len(digests) == 1
    assert digests[0]["status"] == "outbox"
    assert digests[0]["sources"][0]["url"] == "https://example.com/agent-harness"
    assert (Path(test_settings.app_workspace_dir) / "digests" / "e2e.md").exists()

    outbox_files = list((Path(test_settings.app_workspace_dir) / "outbox").glob("*.json"))
    assert len(outbox_files) == 1
    outbox = json.loads(outbox_files[0].read_text(encoding="utf-8"))
    assert outbox["recipient"] == "candidate@example.com"
    assert "agent harness release" in outbox["content"]
