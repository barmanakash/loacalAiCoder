"""
Pydantic schemas for request/response models and internal agent state.
"""

from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field
import uuid


class AgentState(str, Enum):
    IDLE = "IDLE"
    UNDERSTANDING = "UNDERSTANDING"
    PLANNING = "PLANNING"
    EXECUTING = "EXECUTING"
    VALIDATING = "VALIDATING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class PermissionLevel(int, Enum):
    READ_ONLY = 0       # Read and search
    EDIT_WITH_APPROVAL = 1  # Edit files with approval
    DELETE_INSTALL = 2  # Delete/install with confirmation
    SYSTEM_RESTRICTED = 3   # Restricted system actions


class TaskRequest(BaseModel):
    prompt: str = Field(..., description="The task or question for the agent")
    project_path: str = Field(..., description="Absolute path to the project root")
    permission_level: PermissionLevel = Field(
        default=PermissionLevel.EDIT_WITH_APPROVAL,
        description="Permission level for agent actions"
    )
    model: str = Field(default="qwen2.5-coder:7b", description="Ollama model to use")


class TaskResponse(BaseModel):
    task_id: str
    status: AgentState
    files_changed: int = 0
    result: Optional[str] = None
    error: Optional[str] = None
    steps: list[dict] = []


class TaskStep(BaseModel):
    step_type: str
    description: str
    output: Optional[str] = None
    status: str = "pending"


class AgentPlan(BaseModel):
    goal: str
    steps: list[str]
    estimated_files: list[str] = []
    requires_terminal: bool = False
    requires_git: bool = False


class FileOperation(BaseModel):
    operation: str   # read, create, modify, delete
    path: str
    content: Optional[str] = None
    patch: Optional[str] = None


class TerminalCommand(BaseModel):
    command: str
    working_dir: str
    timeout: int = 30
    capture_output: bool = True


class GitOperation(BaseModel):
    operation: str   # status, diff, commit, branch
    message: Optional[str] = None
    branch: Optional[str] = None


class ProjectInfo(BaseModel):
    path: str
    name: str
    language: Optional[str] = None
    framework: Optional[str] = None
    dependencies: dict[str, str] = {}
    file_count: int = 0
    test_framework: Optional[str] = None


class LLMConfig(BaseModel):
    provider: str = "ollama"
    model: str = "qwen2.5-coder:7b"
    base_url: str = "http://localhost:11434"
    temperature: float = 0.1
    max_tokens: int = 4096
    context_window: int = 8192


class MemoryEntry(BaseModel):
    key: str
    value: Any
    memory_type: str  # "short_term" | "long_term"


class SearchResult(BaseModel):
    file_path: str
    content: str
    score: float
    line_numbers: list[int] = []
