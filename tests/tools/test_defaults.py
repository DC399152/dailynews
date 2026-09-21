from pathlib import Path

import pytest

from app.agent.types import ToolCall
from app.settings import Settings
from app.tools.defaults import build_default_tool_registry

EXPECTED_TOOLS = {
    "bash",
    "fetch_article",
    "get_subscription",
    "list_dir",
    "read_file",
    "search_content",
    "search_news",
    "send_digest",
    "write_file",
}


def test_default_registry_contains_all_required_and_product_tools(tmp_path: Path) -> None:
    registry = build_default_tool_registry(Settings(app_workspace_dir=tmp_path / "workspace"))

    assert {definition.name for definition in registry.definitions()} == EXPECTED_TOOLS


@pytest.mark.asyncio
async def test_policy_failure_keeps_specific_error_code_in_observation(tmp_path: Path) -> None:
    registry = build_default_tool_registry(Settings(app_workspace_dir=tmp_path / "workspace"))

    execution = await registry.execute(
        ToolCall(
            id="call-1",
            name="write_file",
            arguments={"path": "../outside.txt", "content": "denied"},
        ),
        timeout_seconds=1,
    )

    assert execution.success is False
    assert execution.error_code == "path_outside_workspace"
