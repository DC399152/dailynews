from collections.abc import Sequence
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import Engine

from app.agent.fake import ScriptedModelClient
from app.agent.types import ModelResponse, ModelUsage, ToolCall
from app.main import create_app
from app.settings import Settings


def successful_responses() -> tuple[ModelResponse, ...]:
    digest = "# Daily AI Brief\n\n- A useful agent engineering update."
    return (
        ModelResponse(
            tool_calls=(
                ToolCall(
                    id="subscription-1",
                    name="get_subscription",
                    arguments={"user_id": "user-1"},
                ),
            ),
            usage=ModelUsage(input_tokens=10, output_tokens=3),
        ),
        ModelResponse(
            tool_calls=(
                ToolCall(
                    id="write-1",
                    name="write_file",
                    arguments={"path": "digests/test.md", "content": digest},
                ),
            ),
            usage=ModelUsage(input_tokens=12, output_tokens=4),
        ),
        ModelResponse(
            tool_calls=(
                ToolCall(
                    id="send-1",
                    name="send_digest",
                    arguments={
                        "user_id": "user-1",
                        "subject": "Daily AI Brief",
                        "content": digest,
                    },
                ),
            ),
            usage=ModelUsage(input_tokens=14, output_tokens=5),
        ),
        ModelResponse(
            content="Digest saved and sent to the development outbox.",
            usage=ModelUsage(input_tokens=8, output_tokens=6),
        ),
    )


def make_client(
    settings: Settings,
    engine: Engine,
    responses: Sequence[ModelResponse] | None = None,
) -> TestClient:
    scripted = tuple(responses or successful_responses())
    app = create_app(
        settings=settings,
        engine=engine,
        model_factory=lambda: ScriptedModelClient(scripted),
    )
    return TestClient(app)


def create_user_and_subscription(client: TestClient) -> None:
    user_response = client.post(
        "/api/users",
        json={
            "user_id": "user-1",
            "identity": "Agent engineering candidate",
            "email": "candidate@example.com",
            "timezone": "Asia/Shanghai",
        },
    )
    assert user_response.status_code == 201
    subscription_response = client.put(
        "/api/users/user-1/subscription",
        json={
            "topics": ["AI agents", "AI coding", "ai AGENTS"],
            "keywords": ["tool calling"],
            "excluded_keywords": ["crypto"],
            "delivery_time": "09:30:00",
            "enabled": True,
        },
    )
    assert subscription_response.status_code == 200


def test_user_and_subscription_crud_normalizes_preferences(
    test_settings: Settings,
    db_engine: Engine,
) -> None:
    with make_client(test_settings, db_engine) as client:
        create_user_and_subscription(client)
        generated_user = client.post(
            "/api/users",
            json={
                "identity": "Second candidate",
                "email": "second@example.com",
                "timezone": "UTC",
            },
        )

        user = client.get("/api/users/user-1")
        subscription = client.get("/api/users/user-1/subscription")

    assert generated_user.status_code == 201
    assert len(generated_user.json()["id"]) == 36
    assert user.status_code == 200
    assert user.json()["timezone"] == "Asia/Shanghai"
    assert subscription.status_code == 200
    assert subscription.json()["topics"] == ["AI agents", "AI coding"]
    assert subscription.json()["delivery_time"] == "09:30:00"


def test_api_uses_consistent_validation_and_not_found_errors(
    test_settings: Settings,
    db_engine: Engine,
) -> None:
    with make_client(test_settings, db_engine) as client:
        invalid = client.post(
            "/api/users",
            json={"identity": "Candidate", "email": "not-an-email", "timezone": "Mars/Base"},
        )
        missing = client.get("/api/users/missing")

    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "validation_error"
    assert missing.status_code == 404
    assert missing.json() == {
        "error": {
            "code": "user_not_found",
            "message": "User does not exist: missing",
            "details": None,
        }
    }


def test_digest_run_persists_trace_digest_and_outbox(
    test_settings: Settings,
    db_engine: Engine,
) -> None:
    with make_client(test_settings, db_engine) as client:
        create_user_and_subscription(client)

        started = client.post("/api/users/user-1/digest-runs")
        assert started.status_code == 202
        run_id = started.json()["id"]

        run = client.get(f"/api/runs/{run_id}")
        tool_calls = client.get(f"/api/runs/{run_id}/tool-calls")
        digests = client.get("/api/users/user-1/digests")

        assert run.status_code == 200
        assert run.json()["status"] == "completed"
        assert run.json()["turn_count"] == 4
        assert run.json()["tool_call_count"] == 3
        assert run.json()["input_tokens"] == 44
        assert run.json()["output_tokens"] == 18
        assert run.json()["digest_id"] is not None

        assert tool_calls.status_code == 200
        assert [call["tool_name"] for call in tool_calls.json()] == [
            "get_subscription",
            "write_file",
            "send_digest",
        ]
        assert all(call["success"] for call in tool_calls.json())

        assert digests.status_code == 200
        assert len(digests.json()) == 1
        digest = digests.json()[0]
        assert digest["title"] == "Daily AI Brief"
        assert digest["status"] == "outbox"
        assert digest["content"].startswith("# Daily AI Brief")
        assert client.get(f"/api/digests/{digest['id']}").status_code == 200

    assert (Path(test_settings.app_workspace_dir) / "digests" / "test.md").exists()
    assert len(list((Path(test_settings.app_workspace_dir) / "outbox").glob("*.json"))) == 1


def test_failed_agent_run_reaches_terminal_state_and_keeps_trace(
    test_settings: Settings,
    db_engine: Engine,
) -> None:
    responses = (
        ModelResponse(
            tool_calls=(
                ToolCall(
                    id="subscription-1",
                    name="get_subscription",
                    arguments={"user_id": "user-1"},
                ),
            )
        ),
        ModelResponse(),
    )
    with make_client(test_settings, db_engine, responses) as client:
        create_user_and_subscription(client)
        started = client.post("/api/users/user-1/digest-runs")
        run_id = started.json()["id"]

        run = client.get(f"/api/runs/{run_id}")
        calls = client.get(f"/api/runs/{run_id}/tool-calls")
        digests = client.get("/api/users/user-1/digests")

    assert run.json()["status"] == "failed"
    assert run.json()["error_code"] == "empty_model_response"
    assert len(calls.json()) == 1
    assert calls.json()[0]["tool_name"] == "get_subscription"
    assert digests.json() == []


def test_start_requires_enabled_subscription_and_blocks_active_duplicate(
    test_settings: Settings,
    db_engine: Engine,
) -> None:
    with make_client(test_settings, db_engine) as client:
        client.post(
            "/api/users",
            json={
                "user_id": "user-1",
                "identity": "Candidate",
                "email": "candidate@example.com",
                "timezone": "UTC",
            },
        )
        without_subscription = client.post("/api/users/user-1/digest-runs")
        client.put(
            "/api/users/user-1/subscription",
            json={"topics": ["agents"], "enabled": True},
        )

        sessions = client.app.state.sessions
        with sessions.begin() as session:
            from app.db.models import AgentRun, RunStatus

            session.add(
                AgentRun(
                    id="active-run",
                    user_id="user-1",
                    status=RunStatus.PENDING,
                    model="fake-model",
                )
            )
        duplicate = client.post("/api/users/user-1/digest-runs")

    assert without_subscription.status_code == 409
    assert without_subscription.json()["error"]["code"] == "subscription_unavailable"
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "run_already_active"
