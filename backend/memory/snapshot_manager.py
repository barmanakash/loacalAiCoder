"""
LocalCoder — Snapshot / Rollback Manager.
Per-task file snapshots; undo, restore, history.
"""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

import aiofiles

from backend.core.config import settings
from backend.core.database import execute, fetch_all
from backend.core.logging import get_logger

log = get_logger(__name__)


class SnapshotManager:
    def __init__(self, project_root: str, task_id: str) -> None:
        self.root    = Path(project_root).resolve()
        self.task_id = task_id
        self.snap_dir = settings.SNAPSHOT_DIR / task_id
        self.snap_dir.mkdir(parents=True, exist_ok=True)

    async def snapshot(self, file_path: str) -> bool:
        """Save current content of a file before modifying it."""
        src = (self.root / file_path).resolve()
        if not src.exists():
            return False

        dest = self.snap_dir / file_path
        dest.parent.mkdir(parents=True, exist_ok=True)

        try:
            async with aiofiles.open(src, encoding="utf-8", errors="replace") as f:
                content = await f.read()

            async with aiofiles.open(dest, "w", encoding="utf-8") as f:
                await f.write(content)

            await execute(
                """
                INSERT INTO snapshots (task_id, file_path, content, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (self.task_id, file_path, content, datetime.utcnow().isoformat()),
            )
            log.debug("snapshot.saved", path=file_path, task=self.task_id)
            return True
        except Exception as exc:
            log.error("snapshot.error", path=file_path, error=str(exc))
            return False

    async def restore(self, file_path: str) -> bool:
        """Restore a file from the latest snapshot for this task."""
        row = await _latest_snapshot(self.task_id, file_path)
        if row is None:
            log.warning("snapshot.not_found", path=file_path)
            return False

        dest = (self.root / file_path).resolve()
        dest.parent.mkdir(parents=True, exist_ok=True)

        try:
            async with aiofiles.open(dest, "w", encoding="utf-8") as f:
                await f.write(row["content"])
            log.info("snapshot.restored", path=file_path)
            return True
        except Exception as exc:
            log.error("snapshot.restore_error", path=file_path, error=str(exc))
            return False

    async def rollback_all(self) -> list[str]:
        """Restore all files snapshotted in this task."""
        rows = await fetch_all(
            "SELECT DISTINCT file_path FROM snapshots WHERE task_id=?", (self.task_id,)
        )
        restored = []
        for row in rows:
            if await self.restore(row["file_path"]):
                restored.append(row["file_path"])
        log.info("snapshot.rollback_all", count=len(restored), task=self.task_id)
        return restored

    async def history(self, file_path: Optional[str] = None) -> list[dict]:
        """Return snapshot history for this task (optionally filtered by file)."""
        if file_path:
            return await fetch_all(
                "SELECT file_path, created_at FROM snapshots WHERE task_id=? AND file_path=? ORDER BY id DESC",
                (self.task_id, file_path),
            )
        return await fetch_all(
            "SELECT file_path, created_at FROM snapshots WHERE task_id=? ORDER BY id DESC",
            (self.task_id,),
        )

    def cleanup(self) -> None:
        """Remove snapshot directory for this task."""
        try:
            shutil.rmtree(self.snap_dir, ignore_errors=True)
        except Exception:
            pass


async def _latest_snapshot(task_id: str, file_path: str):
    from backend.core.database import fetch_one
    return await fetch_one(
        "SELECT content FROM snapshots WHERE task_id=? AND file_path=? ORDER BY id DESC LIMIT 1",
        (task_id, file_path),
    )
