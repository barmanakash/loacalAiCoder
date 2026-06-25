"""
LocalCoder — FastAPI application.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from backend.agent.task_manager import (
    cancel_task, create_task, get_task, list_tasks, submit_task,
)
from backend.core.config import settings
from backend.core.database import init_db
from backend.core.llm import get_llm
from backend.core.logging import get_logger, setup_logging
from backend.memory.context_engine import ContextEngine
from backend.models.types import (
    AgentState, Message, PermissionLevel, TaskRequest, TaskResponse,
)

log = get_logger(__name__)


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    await init_db()
    log.info("localcoder.started", version=settings.APP_VERSION)
    yield
    log.info("localcoder.stopped")


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Local-first autonomous AI coding agent",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health() -> dict:
    llm = get_llm()
    llm_ok = await llm.is_available()
    return {
        "status": "ok" if llm_ok else "degraded",
        "version": settings.APP_VERSION,
        "llm_provider": settings.LLM_PROVIDER.value,
        "llm_model": settings.OLLAMA_MODEL,
        "llm_available": llm_ok,
    }


# ── Tasks ─────────────────────────────────────────────────────────────────────

@app.post("/api/agent/task", response_model=TaskResponse)
async def run_task(request: TaskRequest, background_tasks: BackgroundTasks):
    """
    Submit a task to the agent.
    Runs to completion and returns the result.
    """
    try:
        response = await submit_task(request)
        return response
    except Exception as exc:
        log.error("api.task_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/agent/task/async")
async def run_task_async(request: TaskRequest) -> dict:
    """Submit a task and return immediately with task_id for polling."""
    task_id = await create_task(request)
    asyncio.create_task(_run_bg(task_id, request))
    return {"task_id": task_id, "status": AgentState.IDLE.value}


async def _run_bg(task_id: str, request: TaskRequest) -> None:
    from backend.agent.agent_loop import AgentLoop
    agent = AgentLoop(task_id, request)
    try:
        await agent.run()
    except Exception as exc:
        log.error("bg_task_error", task_id=task_id, error=str(exc))


@app.get("/api/agent/task/{task_id}", response_model=TaskResponse)
async def get_task_status(task_id: str):
    result = await get_task(task_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return result


@app.delete("/api/agent/task/{task_id}")
async def cancel_task_endpoint(task_id: str) -> dict:
    cancelled = await cancel_task(task_id)
    return {"cancelled": cancelled}


@app.get("/api/agent/tasks")
async def list_tasks_endpoint(limit: int = 20, status: str | None = None) -> list:
    return await list_tasks(limit=limit, status=status)


# ── Chat (streaming) ──────────────────────────────────────────────────────────

@app.post("/api/chat/stream")
async def chat_stream(payload: dict[str, Any]):
    """
    Streaming chat endpoint.
    Accepts: {"messages": [...], "system": "..."}
    """
    messages = [Message(**m) for m in payload.get("messages", [])]
    system   = payload.get("system", "")
    llm = get_llm()

    async def generate():
        async for token in llm.stream(messages, system=system):
            yield token

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.post("/api/chat")
async def chat(payload: dict[str, Any]) -> dict:
    """Non-streaming chat."""
    messages = [Message(**m) for m in payload.get("messages", [])]
    system   = payload.get("system", "")
    llm = get_llm()
    response = await llm.chat(messages, system=system)
    return {"content": response}


# ── Repository ────────────────────────────────────────────────────────────────

@app.post("/api/repo/scan")
async def scan_repo(payload: dict[str, str]) -> dict:
    from backend.tools.repo_intelligence import RepoIntelligence
    path = payload.get("path", ".")
    ri = RepoIntelligence(path)
    info = await ri.scan()
    return info.dict()


@app.post("/api/repo/index")
async def index_repo(payload: dict[str, str]) -> dict:
    path = payload.get("path", ".")
    ce = ContextEngine(path)
    chunks = await ce.index_repo()
    return {"indexed_chunks": chunks}


@app.post("/api/repo/search")
async def search_repo(payload: dict[str, Any]) -> list:
    path  = payload.get("path", ".")
    query = payload.get("query", "")
    ce = ContextEngine(path)
    results = await ce.search(query, top_k=payload.get("top_k", 5))
    return results


# ── Memory ────────────────────────────────────────────────────────────────────

@app.post("/api/memory/set")
async def set_memory(payload: dict[str, Any]) -> dict:
    from backend.memory.memory_manager import LongTermMemory
    ltm = LongTermMemory()
    await ltm.set(payload["key"], payload["value"], payload.get("category", "general"))
    return {"ok": True}


@app.get("/api/memory/{key}")
async def get_memory(key: str) -> dict:
    from backend.memory.memory_manager import LongTermMemory
    ltm = LongTermMemory()
    value = await ltm.get(key)
    return {"key": key, "value": value}


# ── LLM Info ─────────────────────────────────────────────────────────────────

@app.get("/api/llm/info")
async def llm_info() -> dict:
    return {
        "provider": settings.LLM_PROVIDER.value,
        "model": settings.OLLAMA_MODEL,
        "base_url": settings.OLLAMA_BASE_URL,
        "temperature": settings.LLM_TEMPERATURE,
        "max_tokens": settings.LLM_MAX_TOKENS,
    }
