from __future__ import annotations

import asyncio
import re
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.tools.errors import ToolPolicyViolation
from app.tools.filesystem import WorkspacePolicy


class BashArguments(BaseModel):
    command: str = Field(min_length=1, max_length=2_000)


@dataclass(frozen=True, slots=True)
class ShellPolicy:
    workspace: WorkspacePolicy
    allowed_commands: frozenset[str] = frozenset(
        {"date", "head", "ls", "pwd", "sort", "tail", "uniq", "wc"}
    )
    max_output_chars: int = 20_000


class RestrictedShellTool:
    _SHELL_SYNTAX = re.compile(r"[;&|><`$(){}\[\]\n\r]")

    def __init__(self, policy: ShellPolicy) -> None:
        self._policy = policy

    async def bash(self, arguments: BashArguments) -> dict[str, Any]:
        command = arguments.command.strip()
        if self._SHELL_SYNTAX.search(command):
            raise ToolPolicyViolation(
                "shell_syntax_denied",
                "Shell operators, substitution, redirection, and control characters are denied",
            )
        try:
            tokens = shlex.split(command, posix=True)
        except ValueError as exc:
            raise ToolPolicyViolation("invalid_command", f"Cannot parse command: {exc}") from exc
        if not tokens:
            raise ToolPolicyViolation("invalid_command", "Command must not be empty")

        executable = Path(tokens[0]).name
        if tokens[0] != executable or executable not in self._policy.allowed_commands:
            raise ToolPolicyViolation(
                "command_denied",
                f"Command is not allowed: {tokens[0]}",
            )
        self._validate_arguments(executable, tokens[1:])

        process = await asyncio.create_subprocess_exec(
            executable,
            *tokens[1:],
            cwd=self._policy.workspace.root,
            env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_bytes, stderr_bytes = await process.communicate()
        except BaseException:
            if process.returncode is None:
                process.kill()
                await process.wait()
            raise

        stdout, stdout_truncated = self._decode_and_cap(stdout_bytes)
        stderr, stderr_truncated = self._decode_and_cap(stderr_bytes)
        return {
            "command": tokens,
            "exit_code": process.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "truncated": stdout_truncated or stderr_truncated,
        }

    def _validate_arguments(self, executable: str, arguments: list[str]) -> None:
        if executable == "pwd" and arguments:
            raise ToolPolicyViolation("arguments_denied", "pwd does not accept arguments")
        if executable == "date":
            if any(not argument.startswith("+") for argument in arguments):
                raise ToolPolicyViolation(
                    "arguments_denied",
                    "date only accepts an optional +FORMAT argument",
                )
            return

        skip_next_number = False
        allowed_flags = {"-a", "-l", "-la", "-al", "-1", "-n", "-c", "-w"}
        for argument in arguments:
            if skip_next_number:
                if not argument.isdigit():
                    raise ToolPolicyViolation("arguments_denied", "Expected a numeric option value")
                skip_next_number = False
                continue
            if argument in {"-n", "-c"} and executable in {"head", "tail"}:
                skip_next_number = True
                continue
            if argument.startswith("-"):
                if argument not in allowed_flags:
                    raise ToolPolicyViolation(
                        "arguments_denied",
                        f"Option is not allowed: {argument}",
                    )
                continue
            self._policy.workspace.resolve(argument)
        if skip_next_number:
            raise ToolPolicyViolation("arguments_denied", "Missing numeric option value")

    def _decode_and_cap(self, value: bytes) -> tuple[str, bool]:
        decoded = value.decode("utf-8", errors="replace")
        if len(decoded) <= self._policy.max_output_chars:
            return decoded, False
        return decoded[: self._policy.max_output_chars], True
