"""
LocalCoder — Memory Manager.
Short-term: current task, conversation, active files.
Long-term: preferences, project rules, architecture decisions (SQLite).
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

from backend.core.database import execute, fetch_all, fetch_one
from backend.core.logging import get_logger
from backend.models.types import Message

log = get_logger(__name__)


class ShortTermMemory:
    """
    In-process memory for the current task.
    Holds: conversation, active files, task context.
    """

    def __init__(self, task_id: str) -> None:
        self.task_id = task_id
        self.messages: list[Message] = []
        self.active_files: list[str] = []
        self.context: dict[str, Any] = {}

    def add_message(self, role: str, content: str) -> None:
        self.messages.append(Message(role=role, content=content))
        log.debug("memory.short.add", role=role, chars=len(content))

    def add_file(self, path: str) -> None:
        if path not in self.active_files:
            self.active_files.append(path)

    def set_context(self, key: str, value: Any) -> None:
        self.context[key] = value

    def get_context(self, key: str, default: Any = None) -> Any:
        return self.context.get(key, default)

    def format_for_llm(self, max_messages: int = 20) -> list[Message]:
        """Return recent messages trimmed to fit context window."""
        return self.messages[-max_messages:]

    async def persist(self) -> None:
        """Flush short-term messages to DB for audit / resume."""
        for msg in self.messages:
            await execute(
                """
                INSERT INTO memory_short (task_id, role, content, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (self.task_id, msg.role, msg.content, msg.created_at.isoformat()),
            )
        log.debug("memory.short.persisted", task_id=self.task_id, count=len(self.messages))


class LongTermMemory:
    """
    Persistent key-value store in SQLite for preferences, rules, decisions.
    """

    async def set(self, key: str, value: Any, category: str = "general") -> None:
        val = json.dumps(value) if not isinstance(value, str) else value
        now = datetime.utcnow().isoformat()
        await execute(
            """
            INSERT INTO memory_long (key, value, category, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value,
                category=excluded.category, updated_at=excluded.updated_at
            """,
            (key, val, category, now),
        )
        log.debug("memory.long.set", key=key, category=category)

    async def get(self, key: str, default: Any = None) -> Any:
        row = await fetch_one("SELECT value FROM memory_long WHERE key=?", (key,))
        if row is None:
            return default
        try:
            return json.loads(row["value"])
        except (json.JSONDecodeError, TypeError):
            return row["value"]

    async def delete(self, key: str) -> None:
        await execute("DELETE FROM memory_long WHERE key=?", (key,))

    async def list_by_category(self, category: str) -> dict[str, Any]:
        rows = await fetch_all(
            "SELECT key, value FROM memory_long WHERE category=?", (category,)
        )
        result = {}
        for row in rows:
            try:
                result[row["key"]] = json.loads(row["value"])
            except Exception:
                result[row["key"]] = row["value"]
        return result

    async def get_project_rules(self, project: str) -> list[str]:
        return await self.get(f"project_rules:{project}", default=[])

    async def set_project_rules(self, project: str, rules: list[str]) -> None:
        await self.set(f"project_rules:{project}", rules, category="project_rules")

    async def get_preferences(self) -> dict[str, Any]:
        return await self.list_by_category("preferences")

    async def set_preference(self, key: str, value: Any) -> None:
        await self.set(f"pref:{key}", value, category="preferences")


class MemoryManager:
    """
    Unified access to short-term and long-term memory.
    One instance per task.
    """

    def __init__(self, task_id: str) -> None:
        self.task_id = task_id
        self.short = ShortTermMemory(task_id)
        self.long = LongTermMemory()

    async def load_system_context(self, project_path: str) -> str:
        """Build system prompt context from long-term memory."""
        prefs = await self.long.get_preferences()
        rules = await self.long.get_project_rules(project_path)

        parts = ["You are LocalCoder, a local-first autonomous AI coding agent."]
        if prefs:
            parts.append(f"User preferences: {json.dumps(prefs)}")
        if rules:
            parts.append("Project rules:\n" + "\n".join(f"- {r}" for r in rules))

        return "\n\n".join(parts)
