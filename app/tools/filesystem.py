from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.tools.errors import ToolFailure, ToolPolicyViolation


class ListDirArguments(BaseModel):
    path: str = "."


class ReadFileArguments(BaseModel):
    path: str


class SearchContentArguments(BaseModel):
    keyword: str = Field(min_length=1, max_length=200)
    dir: str = "."


class WriteFileArguments(BaseModel):
    path: str
    content: str


@dataclass(frozen=True, slots=True)
class WorkspacePolicy:
    root: Path
    max_read_bytes: int = 1_000_000
    max_write_bytes: int = 1_000_000
    max_search_results: int = 100

    def __post_init__(self) -> None:
        root = self.root.expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        object.__setattr__(self, "root", root)
        if min(self.max_read_bytes, self.max_write_bytes, self.max_search_results) <= 0:
            raise ValueError("Workspace limits must be greater than zero")

    def resolve(self, raw_path: str, *, must_exist: bool = True) -> Path:
        if not raw_path or "\x00" in raw_path:
            raise ToolPolicyViolation("invalid_path", "Path must be a non-empty relative path")
        relative = Path(raw_path)
        if relative.is_absolute():
            raise ToolPolicyViolation("path_outside_workspace", "Absolute paths are not allowed")

        candidate = (self.root / relative).resolve(strict=False)
        if not candidate.is_relative_to(self.root):
            raise ToolPolicyViolation(
                "path_outside_workspace",
                "Path escapes the configured workspace",
            )
        if must_exist and not candidate.exists():
            raise ToolFailure("path_not_found", f"Path does not exist: {raw_path}")
        return candidate


class FilesystemTools:
    def __init__(self, policy: WorkspacePolicy) -> None:
        self._policy = policy

    def list_dir(self, arguments: ListDirArguments) -> dict[str, Any]:
        directory = self._policy.resolve(arguments.path)
        if not directory.is_dir():
            raise ToolFailure("not_a_directory", f"Not a directory: {arguments.path}")

        entries = []
        for entry in sorted(directory.iterdir(), key=lambda item: item.name.casefold()):
            safe_entry = self._policy.resolve(str(entry.relative_to(self._policy.root)))
            entries.append(
                {
                    "name": entry.name,
                    "type": "directory" if safe_entry.is_dir() else "file",
                    "size": safe_entry.stat().st_size if safe_entry.is_file() else None,
                }
            )
        return {"path": self._display_path(directory), "entries": entries}

    def read_file(self, arguments: ReadFileArguments) -> dict[str, Any]:
        path = self._policy.resolve(arguments.path)
        if not path.is_file():
            raise ToolFailure("not_a_file", f"Not a file: {arguments.path}")
        size = path.stat().st_size
        if size > self._policy.max_read_bytes:
            raise ToolPolicyViolation(
                "file_too_large",
                f"File is {size} bytes; limit is {self._policy.max_read_bytes}",
            )
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise ToolFailure(
                "unsupported_encoding",
                "Only UTF-8 text files are supported",
            ) from exc
        return {"path": self._display_path(path), "content": content, "size": size}

    def search_content(self, arguments: SearchContentArguments) -> dict[str, Any]:
        directory = self._policy.resolve(arguments.dir)
        if not directory.is_dir():
            raise ToolFailure("not_a_directory", f"Not a directory: {arguments.dir}")

        needle = arguments.keyword.casefold()
        matches: list[dict[str, Any]] = []
        skipped_files = 0
        for current_root, directory_names, file_names in os.walk(directory, followlinks=False):
            current = Path(current_root)
            directory_names[:] = [
                name for name in directory_names if not (current / name).is_symlink()
            ]
            for file_name in sorted(file_names):
                raw_path = current / file_name
                try:
                    path = self._policy.resolve(str(raw_path.relative_to(self._policy.root)))
                except ToolPolicyViolation:
                    skipped_files += 1
                    continue
                if not path.is_file() or path.stat().st_size > self._policy.max_read_bytes:
                    skipped_files += 1
                    continue
                try:
                    with path.open(encoding="utf-8") as handle:
                        for line_number, line in enumerate(handle, start=1):
                            if needle in line.casefold():
                                matches.append(
                                    {
                                        "path": self._display_path(path),
                                        "line": line_number,
                                        "text": line.rstrip("\n")[:500],
                                    }
                                )
                                if len(matches) >= self._policy.max_search_results:
                                    return {
                                        "keyword": arguments.keyword,
                                        "matches": matches,
                                        "truncated": True,
                                        "skipped_files": skipped_files,
                                    }
                except (OSError, UnicodeDecodeError):
                    skipped_files += 1

        return {
            "keyword": arguments.keyword,
            "matches": matches,
            "truncated": False,
            "skipped_files": skipped_files,
        }

    def write_file(self, arguments: WriteFileArguments) -> dict[str, Any]:
        encoded = arguments.content.encode("utf-8")
        if len(encoded) > self._policy.max_write_bytes:
            raise ToolPolicyViolation(
                "content_too_large",
                f"Content is {len(encoded)} bytes; limit is {self._policy.max_write_bytes}",
            )

        path = self._policy.resolve(arguments.path, must_exist=False)
        if path.exists() and not path.is_file():
            raise ToolFailure("not_a_file", f"Not a file: {arguments.path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        safe_parent = self._policy.resolve(str(path.parent.relative_to(self._policy.root)))

        file_descriptor, temporary_name = tempfile.mkstemp(prefix=".agent-write-", dir=safe_parent)
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(file_descriptor, "wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, path)
        finally:
            temporary_path.unlink(missing_ok=True)

        return {"path": self._display_path(path), "bytes_written": len(encoded)}

    def _display_path(self, path: Path) -> str:
        relative = path.relative_to(self._policy.root)
        return "." if relative == Path(".") else relative.as_posix()
