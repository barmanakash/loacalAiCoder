"""
LocalCoder — Git Agent.
Status, diff, commit generation, branch management.
"""

from __future__ import annotations

import asyncio
import shlex
from pathlib import Path
from typing import Optional

from backend.core.logging import get_logger
from backend.models.types import PermissionLevel, ToolResult
from backend.tools.terminal_agent import TerminalAgent

log = get_logger(__name__)


class GitAgent:
    def __init__(
        self,
        project_root: str,
        task_id: str,
        permission_level: PermissionLevel = PermissionLevel.EDIT,
    ) -> None:
        self.root = str(Path(project_root).resolve())
        self.task_id = task_id
        self._terminal = TerminalAgent(
            cwd=self.root,
            task_id=task_id,
            permission_level=permission_level,
        )

    async def _git(self, *args: str) -> ToolResult:
        cmd = "git " + " ".join(shlex.quote(a) for a in args)
        return await self._terminal.run(cmd, timeout=30)

    async def is_repo(self) -> bool:
        r = await self._git("rev-parse", "--is-inside-work-tree")
        return r.success and r.output.strip() == "true"

    async def status(self) -> ToolResult:
        """Return git status (short format)."""
        return await self._git("status", "--short", "--branch")

    async def diff(self, staged: bool = False) -> ToolResult:
        """Return diff of working tree or staged changes."""
        args = ["diff"]
        if staged:
            args.append("--cached")
        return await self._git(*args)

    async def diff_file(self, path: str) -> ToolResult:
        return await self._git("diff", "--", path)

    async def log(self, n: int = 10) -> ToolResult:
        return await self._git(
            "log", f"-{n}", "--oneline", "--decorate", "--graph"
        )

    async def current_branch(self) -> str:
        r = await self._git("branch", "--show-current")
        return r.output.strip() if r.success else "unknown"

    async def create_branch(self, name: str) -> ToolResult:
        return await self._git("checkout", "-b", name)

    async def switch_branch(self, name: str) -> ToolResult:
        return await self._git("checkout", name)

    async def stage(self, paths: list[str] | None = None) -> ToolResult:
        if paths:
            return await self._git("add", "--", *paths)
        return await self._git("add", "-A")

    async def commit(self, message: str, author: str = "LocalCoder <localcoder@local>") -> ToolResult:
        return await self._git(
            "commit",
            "--author", author,
            "-m", message,
        )

    async def generate_commit_message(self, llm, changed_files: list[str]) -> str:
        """Use LLM to generate a conventional commit message from the diff."""
        diff_result = await self.diff(staged=True)
        diff_text = diff_result.output[:4000] if diff_result.success else ""

        from backend.models.types import Message

        messages = [
            Message(
                role="user",
                content=(
                    f"Generate a concise git commit message (conventional commit format) "
                    f"for these changes.\n\nChanged files: {', '.join(changed_files)}\n\n"
                    f"Diff:\n{diff_text}\n\n"
                    "Reply with ONLY the commit message, no explanation."
                ),
            )
        ]
        try:
            msg = await llm.chat(messages, temperature=0.3)
            return msg.strip().strip('"').strip("'")
        except Exception:
            return f"chore: update {', '.join(changed_files[:3])}"

    async def stash(self) -> ToolResult:
        return await self._git("stash")

    async def stash_pop(self) -> ToolResult:
        return await self._git("stash", "pop")

    async def reset_file(self, path: str) -> ToolResult:
        """Restore a file to HEAD."""
        return await self._git("checkout", "HEAD", "--", path)
