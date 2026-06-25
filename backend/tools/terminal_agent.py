"""
LocalCoder — Terminal Agent.
Execute shell commands safely with timeout, sandbox, and output capture.
"""

from __future__ import annotations

import asyncio
import os
import re
import shlex
from pathlib import Path
from typing import Optional

from backend.core.config import settings
from backend.core.logging import get_logger
from backend.core.permissions import request_approval
from backend.models.types import PermissionLevel, ToolResult

log = get_logger(__name__)

# Commands that always require level 2+ approval
DESTRUCTIVE_PATTERNS = [
    r"\brm\s+-rf\b", r"\bdd\b", r"\bmkfs\b", r"\bformat\b",
    r"\bdrop\s+database\b", r"\btruncate\b",
    r"\bsudo\b", r"\bsu\s", r"\bchown\b", r"\bchmod\s+777\b",
    r"\bcurl\b.*\|\s*(bash|sh|python)",
    r"\bwget\b.*\|\s*(bash|sh|python)",
    r"\bnpm\s+(install|i)\b", r"\bpip\s+install\b", r"\bapt\b", r"\byum\b", r"\bbrew\b",
]

BLOCKED_PATTERNS = [
    r"\brm\s+-rf\s+/",     # rm -rf /
    r"\bmkfs\b",
    r":\(\)\{.*\};:",      # fork bomb
]


def _classify(cmd: str) -> PermissionLevel:
    for p in BLOCKED_PATTERNS:
        if re.search(p, cmd, re.IGNORECASE):
            return PermissionLevel.SYSTEM  # will be rejected

    for p in DESTRUCTIVE_PATTERNS:
        if re.search(p, cmd, re.IGNORECASE):
            return PermissionLevel.DESTRUCTIVE

    return PermissionLevel.EDIT


class TerminalAgent:
    def __init__(
        self,
        cwd: str,
        task_id: str,
        permission_level: PermissionLevel = PermissionLevel.EDIT,
    ) -> None:
        self.cwd = str(Path(cwd).resolve())
        self.task_id = task_id
        self.permission_level = permission_level
        self._history: list[dict] = []

    async def run(
        self,
        command: str,
        timeout: Optional[int] = None,
        env_extra: Optional[dict[str, str]] = None,
    ) -> ToolResult:
        """
        Execute a shell command in the project directory.
        Returns stdout + stderr combined, truncated to MAX_OUTPUT chars.
        """
        cmd_timeout = timeout or settings.TERMINAL_TIMEOUT
        required_level = _classify(command)

        # Block outright dangerous commands
        if required_level == PermissionLevel.SYSTEM:
            return ToolResult(
                tool_name="terminal_run",
                success=False,
                error=f"Command blocked (system-level danger): {command}",
            )

        approved = await request_approval(
            action=f"Execute: {command}",
            details=f"cwd={self.cwd}",
            required_level=required_level,
            task_id=self.task_id,
            current_level=self.permission_level,
        )
        if not approved:
            return ToolResult(tool_name="terminal_run", success=False, error="Permission denied")

        # Build environment
        env = os.environ.copy()
        env["TERM"] = "dumb"
        env["NO_COLOR"] = "1"
        if env_extra:
            env.update(env_extra)

        log.info("terminal.run", command=command, cwd=self.cwd, timeout=cmd_timeout)
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=self.cwd,
                env=env,
            )
            try:
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=cmd_timeout)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.communicate()
                return ToolResult(
                    tool_name="terminal_run",
                    success=False,
                    error=f"Command timed out after {cmd_timeout}s: {command}",
                )

            output = stdout.decode("utf-8", errors="replace")
            if len(output) > settings.TERMINAL_MAX_OUTPUT:
                output = output[-settings.TERMINAL_MAX_OUTPUT:] + "\n[...truncated]"

            success = proc.returncode == 0
            self._history.append(
                {"command": command, "exit_code": proc.returncode, "output_length": len(output)}
            )

            log.info("terminal.result", command=command, exit_code=proc.returncode)
            return ToolResult(
                tool_name="terminal_run",
                success=success,
                output=output,
                error="" if success else f"Exit code {proc.returncode}",
                metadata={"exit_code": proc.returncode, "cwd": self.cwd},
            )

        except Exception as exc:
            log.error("terminal.error", command=command, error=str(exc))
            return ToolResult(tool_name="terminal_run", success=False, error=str(exc))

    async def which(self, binary: str) -> bool:
        """Check if a binary is available on PATH."""
        result = await self.run(f"which {shlex.quote(binary)}", timeout=5)
        return result.success

    @property
    def history(self) -> list[dict]:
        return list(self._history)
