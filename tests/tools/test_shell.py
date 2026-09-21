from pathlib import Path

import pytest

from app.tools.errors import ToolPolicyViolation
from app.tools.filesystem import WorkspacePolicy
from app.tools.shell import BashArguments, RestrictedShellTool, ShellPolicy


def make_shell(tmp_path: Path, *, max_output_chars: int = 20_000) -> RestrictedShellTool:
    workspace = WorkspacePolicy(tmp_path / "workspace")
    return RestrictedShellTool(ShellPolicy(workspace=workspace, max_output_chars=max_output_chars))


@pytest.mark.asyncio
async def test_shell_runs_allowlisted_command_in_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "brief.md").write_text("brief", encoding="utf-8")
    shell = make_shell(tmp_path)

    result = await shell.bash(BashArguments(command="ls -1 ."))

    assert result["exit_code"] == 0
    assert result["stdout"] == "brief.md\n"
    assert result["stderr"] == ""


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("command", "expected_code"),
    [
        ("rm brief.md", "command_denied"),
        ("ls .; whoami", "shell_syntax_denied"),
        ("ls ../", "path_outside_workspace"),
        ("/bin/ls", "command_denied"),
    ],
)
async def test_shell_rejects_dangerous_commands(
    tmp_path: Path,
    command: str,
    expected_code: str,
) -> None:
    shell = make_shell(tmp_path)

    with pytest.raises(ToolPolicyViolation) as error:
        await shell.bash(BashArguments(command=command))

    assert error.value.code == expected_code


@pytest.mark.asyncio
async def test_shell_caps_output(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "long.txt").write_text("1234567890", encoding="utf-8")
    shell = make_shell(tmp_path, max_output_chars=4)

    result = await shell.bash(BashArguments(command="head long.txt"))

    assert result["stdout"] == "1234"
    assert result["truncated"] is True
