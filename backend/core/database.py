"""
LocalCoder — Async SQLite database layer (aiosqlite).
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import datetime
from typing import AsyncGenerator, Any

import aiosqlite

from backend.core.config import settings
from backend.core.logging import get_logger

log = get_logger(__name__)

DB_PATH = str(settings.DB_PATH)

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id          TEXT PRIMARY KEY,
    prompt      TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'IDLE',
    result      TEXT,
    error       TEXT,
    files_changed INTEGER DEFAULT 0,
    steps       TEXT DEFAULT '[]',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    project_path TEXT
);

CREATE TABLE IF NOT EXISTS memory_short (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id     TEXT NOT NULL,
    role        TEXT NOT NULL,
    content     TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    FOREIGN KEY (task_id) REFERENCES tasks(id)
);

CREATE TABLE IF NOT EXISTS memory_long (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    key         TEXT NOT NULL UNIQUE,
    value       TEXT NOT NULL,
    category    TEXT NOT NULL DEFAULT 'general',
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS snapshots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id     TEXT NOT NULL,
    file_path   TEXT NOT NULL,
    content     TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id     TEXT,
    action      TEXT NOT NULL,
    details     TEXT,
    level       INTEGER NOT NULL DEFAULT 1,
    approved    INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tasks_status   ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_memory_task    ON memory_short(task_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_task ON snapshots(task_id);
CREATE INDEX IF NOT EXISTS idx_audit_task     ON audit_log(task_id);
"""


@asynccontextmanager
async def get_db() -> AsyncGenerator[aiosqlite.Connection, None]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA foreign_keys=ON")
        yield db


async def init_db() -> None:
    """Create tables if they don't exist."""
    async with get_db() as db:
        await db.executescript(SCHEMA)
        await db.commit()
    log.info("database.initialized", path=DB_PATH)


async def fetch_one(query: str, params: tuple = ()) -> dict[str, Any] | None:
    async with get_db() as db:
        async with db.execute(query, params) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def fetch_all(query: str, params: tuple = ()) -> list[dict[str, Any]]:
    async with get_db() as db:
        async with db.execute(query, params) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def execute(query: str, params: tuple = ()) -> int:
    async with get_db() as db:
        cur = await db.execute(query, params)
        await db.commit()
        return cur.lastrowid or 0
