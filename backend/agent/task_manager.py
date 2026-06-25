"""
LocalCoder — Task Manager.
Creates, tracks, and cancels agent tasks.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import Optional

from backend.agent.agent_loop import AgentLoop
from backend.core.database import execute, fetch_all, fetch_one
from backend.core.llm import get_llm
from backend.core.logging import get_logger
from backend.models.types import AgentState, TaskRequest, TaskResponse

log = get_logger(__name__)

# In-memory registry of running tasks
_running: dict[str, asyncio.Task] = {}
_agents:  dict[str, AgentLoop]    = {}


async def create_task(request: TaskRequest) -> str:
    """Persist a new task record and return its ID."""
    task_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    await execute(
        """
        INSERT INTO tasks (id, prompt, status, created_at, updated_at, project_path)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (task_id, request.prompt, AgentState.IDLE.value, now, now, request.project_path),
    )
    log.info("task.created", task_id=task_id, prompt=request.prompt[:80])
    return task_id


async def submit_task(request: TaskRequest) -> TaskResponse:
    """Create a task and run it to completion (blocking)."""
    task_id = await create_task(request)
    agent   = AgentLoop(task_id, request, llm=get_llm())
    _agents[task_id] = agent

    loop = asyncio.get_event_loop()
    fut  = loop.create_task(agent.run())
    _running[task_id] = fut

    try:
        result = await asyncio.wait_for(fut, timeout=request.context.get("timeout", 600))
    except asyncio.TimeoutError:
        agent.cancel()
        fut.cancel()
        log.error("task.timeout", task_id=task_id)
        result = TaskResponse(
            task_id=task_id,
            status=AgentState.FAILED,
            error="Task timed out",
        )
    finally:
        _running.pop(task_id, None)
        _agents.pop(task_id, None)

    return result


async def get_task(task_id: str) -> Optional[TaskResponse]:
    """Fetch task status from DB."""
    row = await fetch_one("SELECT * FROM tasks WHERE id=?", (task_id,))
    if row is None:
        return None
    import json
    return TaskResponse(
        task_id=row["id"],
        status=AgentState(row["status"]),
        result=row.get("result"),
        error=row.get("error"),
        files_changed=row.get("files_changed", 0),
        steps=json.loads(row.get("steps") or "[]"),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


async def cancel_task(task_id: str) -> bool:
    """Cancel a running task."""
    if task_id in _running:
        _running[task_id].cancel()
        if task_id in _agents:
            _agents[task_id].cancel()
        log.info("task.cancelled", task_id=task_id)
        return True
    return False


async def list_tasks(limit: int = 50, status: Optional[str] = None) -> list[dict]:
    """List recent tasks."""
    if status:
        return await fetch_all(
            "SELECT id, prompt, status, files_changed, created_at FROM tasks WHERE status=? ORDER BY created_at DESC LIMIT ?",
            (status, limit),
        )
    return await fetch_all(
        "SELECT id, prompt, status, files_changed, created_at FROM tasks ORDER BY created_at DESC LIMIT ?",
        (limit,),
    )
