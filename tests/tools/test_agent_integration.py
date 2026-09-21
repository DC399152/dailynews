from pathlib import Path

import pytest

from app.agent.fake import ScriptedModelClient
from app.agent.loop import AgentLoop
from app.agent.types import ModelResponse, ToolCall
from app.settings import Settings
from app.tools.defaults import build_default_tool_registry


@pytest.mark.asyncio
async def test_agent_loop_uses_real_workspace_tools_and_observations(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    model = ScriptedModelClient(
        [
            ModelResponse(
                tool_calls=(
                    ToolCall(
                        id="write-1",
                        name="write_file",
                        arguments={"path": "digest.md", "content": "Agent news"},
                    ),
                )
            ),
            ModelResponse(
                tool_calls=(
                    ToolCall(
                        id="read-1",
                        name="read_file",
                        arguments={"path": "digest.md"},
                    ),
                )
            ),
            ModelResponse(content="Digest written and verified."),
        ]
    )
    loop = AgentLoop(
        model=model,
        tools=build_default_tool_registry(Settings(app_workspace_dir=workspace)),
    )

    result = await loop.run(goal="Create a digest", system_prompt="Use tools as needed")

    assert result.final_output == "Digest written and verified."
    assert result.tool_calls == 2
    assert (workspace / "digest.md").read_text(encoding="utf-8") == "Agent news"
    assert '"bytes_written": 10' in (model.requests[1][0][-1].content or "")
    assert '"content": "Agent news"' in (model.requests[2][0][-1].content or "")
