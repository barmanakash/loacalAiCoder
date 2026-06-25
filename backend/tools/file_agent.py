"""
LocalCoder — File Agent.
Read, create, modify files, generate patches, show diffs.
"""

from __future__ import annotations

import difflib
import os
import shutil
from pathlib import Path
from typing import Optional

import aiofiles

from backend.core.logging import get_logger
from backend.core.permissions import request_approval
from backend.models.types import PermissionLevel, ToolResult

log = get_logger(__name__)

# Extensions considered safe to read (expandable)
SAFE_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".html", ".css", ".scss",
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf",
    ".md", ".txt", ".rst", ".sh", ".bash", ".zsh", ".fish",
    ".go", ".rs", ".c", ".cpp", ".h", ".hpp", ".java", ".kt",
    ".rb", ".php", ".swift", ".dart", ".lua", ".r", ".sql",
    ".env", ".gitignore", ".dockerignore", "Dockerfile", "Makefile",
}

MAX_FILE_SIZE = 2 * 1024 * 1024  # 2 MB read limit


class FileAgent:
    def __init__(
        self,
        project_root: str,
        task_id: str,
        permission_level: PermissionLevel = PermissionLevel.EDIT,
        snapshot_dir: Optional[str] = None,
    ) -> None:
        self.root = Path(project_root).resolve()
        self.task_id = task_id
        self.permission_level = permission_level
        self.snapshot_dir = Path(snapshot_dir) if snapshot_dir else None
        self._changed_files: list[str] = []

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _resolve(self, path: str) -> Path:
        p = (self.root / path).resolve()
        if not str(p).startswith(str(self.root)):
            raise PermissionError(f"Path escapes project root: {path}")
        return p

    def _is_safe(self, path: Path) -> bool:
        return path.suffix in SAFE_EXTENSIONS or path.name in SAFE_EXTENSIONS

    async def _snapshot(self, path: Path) -> None:
        if self.snapshot_dir and path.exists():
            rel = path.relative_to(self.root)
            dest = self.snapshot_dir / self.task_id / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)
            log.debug("file.snapshot", path=str(path))

    # ── Public API ────────────────────────────────────────────────────────────

    async def read(self, path: str) -> ToolResult:
        """Read a file and return its contents."""
        try:
            p = self._resolve(path)
            if not p.exists():
                return ToolResult(tool_name="file_read", success=False, error=f"File not found: {path}")
            if not self._is_safe(p):
                return ToolResult(tool_name="file_read", success=False, error=f"Unsafe file type: {p.suffix}")
            if p.stat().st_size > MAX_FILE_SIZE:
                return ToolResult(tool_name="file_read", success=False, error="File too large (>2MB)")

            async with aiofiles.open(p, encoding="utf-8", errors="replace") as f:
                content = await f.read()

            log.info("file.read", path=path, size=len(content))
            return ToolResult(
                tool_name="file_read",
                success=True,
                output=content,
                metadata={"path": str(p), "lines": content.count("\n") + 1, "size": len(content)},
            )
        except Exception as exc:
            log.error("file.read.error", path=path, error=str(exc))
            return ToolResult(tool_name="file_read", success=False, error=str(exc))

    async def create(self, path: str, content: str) -> ToolResult:
        """Create a new file."""
        approved = await request_approval(
            action=f"Create file: {path}",
            details=f"Content length: {len(content)} chars",
            required_level=PermissionLevel.EDIT,
            task_id=self.task_id,
            current_level=self.permission_level,
        )
        if not approved:
            return ToolResult(tool_name="file_create", success=False, error="Permission denied")

        try:
            p = self._resolve(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            async with aiofiles.open(p, "w", encoding="utf-8") as f:
                await f.write(content)
            self._changed_files.append(str(p.relative_to(self.root)))
            log.info("file.created", path=path)
            return ToolResult(tool_name="file_create", success=True, output=f"Created: {path}")
        except Exception as exc:
            return ToolResult(tool_name="file_create", success=False, error=str(exc))

    async def modify(self, path: str, content: str) -> ToolResult:
        """Overwrite a file with new content (snapshot first)."""
        approved = await request_approval(
            action=f"Modify file: {path}",
            details=f"New content: {len(content)} chars",
            required_level=PermissionLevel.EDIT,
            task_id=self.task_id,
            current_level=self.permission_level,
        )
        if not approved:
            return ToolResult(tool_name="file_modify", success=False, error="Permission denied")

        try:
            p = self._resolve(path)
            await self._snapshot(p)

            old_content = ""
            if p.exists():
                async with aiofiles.open(p, encoding="utf-8", errors="replace") as f:
                    old_content = await f.read()

            async with aiofiles.open(p, "w", encoding="utf-8") as f:
                await f.write(content)

            diff = self._diff(old_content, content, path)
            self._changed_files.append(str(p.relative_to(self.root)))
            log.info("file.modified", path=path)
            return ToolResult(
                tool_name="file_modify",
                success=True,
                output=f"Modified: {path}\n\n{diff}",
                metadata={"diff": diff},
            )
        except Exception as exc:
            return ToolResult(tool_name="file_modify", success=False, error=str(exc))

    async def delete(self, path: str) -> ToolResult:
        """Delete a file (requires level 2)."""
        approved = await request_approval(
            action=f"Delete file: {path}",
            details="This action is irreversible without snapshot.",
            required_level=PermissionLevel.DESTRUCTIVE,
            task_id=self.task_id,
            current_level=self.permission_level,
        )
        if not approved:
            return ToolResult(tool_name="file_delete", success=False, error="Permission denied")

        try:
            p = self._resolve(path)
            await self._snapshot(p)
            p.unlink()
            log.info("file.deleted", path=path)
            return ToolResult(tool_name="file_delete", success=True, output=f"Deleted: {path}")
        except Exception as exc:
            return ToolResult(tool_name="file_delete", success=False, error=str(exc))

    async def apply_patch(self, path: str, patch: str) -> ToolResult:
        """Apply a unified diff patch to a file."""
        result = await self.read(path)
        if not result.success:
            return result

        try:
            old_lines = result.output.splitlines(keepends=True)
            patched_lines = list(
                difflib.restore(patch.splitlines(keepends=True), 2)
            )
            new_content = "".join(patched_lines)
            return await self.modify(path, new_content)
        except Exception as exc:
            return ToolResult(tool_name="file_patch", success=False, error=str(exc))

    async def diff(self, path: str, new_content: str) -> ToolResult:
        """Show diff between current file and proposed content."""
        result = await self.read(path)
        old_content = result.output if result.success else ""
        diff_text = self._diff(old_content, new_content, path)
        return ToolResult(
            tool_name="file_diff",
            success=True,
            output=diff_text,
            metadata={"path": path},
        )

    async def list_dir(self, path: str = ".") -> ToolResult:
        """List directory contents."""
        try:
            p = self._resolve(path)
            entries = []
            for item in sorted(p.iterdir()):
                rel = item.relative_to(self.root)
                kind = "dir" if item.is_dir() else "file"
                entries.append(f"[{kind}] {rel}")
            return ToolResult(
                tool_name="file_list",
                success=True,
                output="\n".join(entries),
                metadata={"count": len(entries)},
            )
        except Exception as exc:
            return ToolResult(tool_name="file_list", success=False, error=str(exc))

    @property
    def changed_files(self) -> list[str]:
        return list(set(self._changed_files))

    # ── Static helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _diff(old: str, new: str, path: str) -> str:
        return "".join(
            difflib.unified_diff(
                old.splitlines(keepends=True),
                new.splitlines(keepends=True),
                fromfile=f"a/{path}",
                tofile=f"b/{path}",
                lineterm="",
            )
        )
