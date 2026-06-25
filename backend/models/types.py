"""
LocalCoder — Shared Pydantic models and enums.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


# ── Agent State Machine ───────────────────────────────────────────────────────

class AgentState(str, Enum):
    IDLE        = "IDLE"
    UNDERSTANDING = "UNDERSTANDING"
    PLANNING    = "PLANNING"
    EXECUTING   = "EXECUTING"
    VALIDATING  = "VALIDATING"
    COMPLETED   = "COMPLETED"
    FAILED      = "FAILED"


class PermissionLevel(int, Enum):
    READ       = 0   # read & search only
    EDIT       = 1   # edit files (with approval)
    DESTRUCTIVE = 2  # delete / install (with confirmation)
    SYSTEM     = 3   # restricted system actions


# ── Tool Models ───────────────────────────────────────────────────────────────

class ToolCall(BaseModel):
    name: str
    args: dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    tool_name: str
    success: bool
    output: str = ""
    error: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


# ── Plan / Step ───────────────────────────────────────────────────────────────

class PlanStep(BaseModel):
    step_id: int
    description: str
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[int] = Field(default_factory=list)
    status: str = "pending"   # pending | running | done | failed
    result: Optional[ToolResult] = None


class Plan(BaseModel):
    goal: str
    steps: list[PlanStep]
    reasoning: str = ""


# ── Task ─────────────────────────────────────────────────────────────────────

class TaskRequest(BaseModel):
    prompt: str
    project_path: Optional[str] = None
    permission_level: PermissionLevel = PermissionLevel.EDIT
    context: dict[str, Any] = Field(default_factory=dict)


class TaskResponse(BaseModel):
    task_id: str
    status: AgentState
    result: Optional[str] = None
    error: Optional[str] = None
    files_changed: int = 0
    steps: list[dict] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# ── Memory ────────────────────────────────────────────────────────────────────

class Message(BaseModel):
    role: str   # user | assistant | system | tool
    content: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class LongTermMemory(BaseModel):
    key: str
    value: str
    category: str = "general"
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# ── Repository ────────────────────────────────────────────────────────────────

class FileInfo(BaseModel):
    path: str
    language: Optional[str] = None
    size: int = 0
    lines: int = 0


class RepoInfo(BaseModel):
    root: str
    languages: dict[str, int] = Field(default_factory=dict)   # lang -> file count
    frameworks: list[str] = Field(default_factory=list)
    dependencies: dict[str, list[str]] = Field(default_factory=dict)
    files: list[FileInfo] = Field(default_factory=list)
    total_files: int = 0
    total_lines: int = 0


# ── Approval ──────────────────────────────────────────────────────────────────

class ApprovalRequest(BaseModel):
    action: str
    details: str
    permission_level: PermissionLevel
    task_id: str


class ApprovalResponse(BaseModel):
    approved: bool
    reason: str = ""
