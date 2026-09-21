from pathlib import Path

import pytest

from app.tools.errors import ToolPolicyViolation
from app.tools.filesystem import (
    FilesystemTools,
    ListDirArguments,
    ReadFileArguments,
    SearchContentArguments,
    WorkspacePolicy,
    WriteFileArguments,
)


def make_tools(root: Path, **limits: int) -> FilesystemTools:
    return FilesystemTools(WorkspacePolicy(root=root, **limits))


def test_filesystem_tools_complete_write_read_list_and_search_flow(tmp_path: Path) -> None:
    tools = make_tools(tmp_path / "workspace")

    write_result = tools.write_file(
        WriteFileArguments(path="digests/today.md", content="AI agents\nTool calling\n")
    )
    read_result = tools.read_file(ReadFileArguments(path="digests/today.md"))
    list_result = tools.list_dir(ListDirArguments(path="digests"))
    search_result = tools.search_content(SearchContentArguments(keyword="tool", dir="digests"))

    assert write_result == {"path": "digests/today.md", "bytes_written": 23}
    assert read_result["content"] == "AI agents\nTool calling\n"
    assert list_result["entries"] == [{"name": "today.md", "type": "file", "size": 23}]
    assert search_result["matches"] == [
        {"path": "digests/today.md", "line": 2, "text": "Tool calling"}
    ]
    assert not list((tmp_path / "workspace" / "digests").glob(".agent-write-*"))


@pytest.mark.parametrize("path", ["../outside.txt", "/etc/passwd"])
def test_filesystem_rejects_paths_outside_workspace(tmp_path: Path, path: str) -> None:
    tools = make_tools(tmp_path / "workspace")

    with pytest.raises(ToolPolicyViolation) as error:
        tools.write_file(WriteFileArguments(path=path, content="denied"))

    assert error.value.code == "path_outside_workspace"


def test_filesystem_rejects_symlink_escape(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside"
    outside.mkdir()
    workspace.mkdir()
    (workspace / "escape").symlink_to(outside, target_is_directory=True)
    tools = make_tools(workspace)

    with pytest.raises(ToolPolicyViolation) as error:
        tools.write_file(WriteFileArguments(path="escape/stolen.txt", content="denied"))

    assert error.value.code == "path_outside_workspace"
    assert not (outside / "stolen.txt").exists()


def test_filesystem_enforces_read_and_write_size_limits(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    tools = make_tools(workspace, max_read_bytes=4, max_write_bytes=4)

    with pytest.raises(ToolPolicyViolation) as write_error:
        tools.write_file(WriteFileArguments(path="large.txt", content="12345"))
    assert write_error.value.code == "content_too_large"

    (workspace / "large.txt").write_text("12345", encoding="utf-8")
    with pytest.raises(ToolPolicyViolation) as read_error:
        tools.read_file(ReadFileArguments(path="large.txt"))
    assert read_error.value.code == "file_too_large"


def test_search_stops_at_configured_result_limit(tmp_path: Path) -> None:
    tools = make_tools(tmp_path / "workspace", max_search_results=1)
    tools.write_file(WriteFileArguments(path="one.txt", content="agent\nagent\n"))

    result = tools.search_content(SearchContentArguments(keyword="agent"))

    assert len(result["matches"]) == 1
    assert result["truncated"] is True
