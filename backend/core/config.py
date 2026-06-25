"""
LocalCoder AI Agent — Core Configuration
"""

from __future__ import annotations

import os
from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings


class LLMProvider(str, Enum):
    OLLAMA = "ollama"
    LLAMA_CPP = "llama_cpp"
    OPENAI_COMPAT = "openai_compat"


class VectorStore(str, Enum):
    CHROMA = "chroma"
    LANCE = "lance"


class Settings(BaseSettings):
    # ── App ───────────────────────────────────────────────────────────────────
    APP_NAME: str = "LocalCoder AI Agent"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # ── Paths ─────────────────────────────────────────────────────────────────
    BASE_DIR: Path = Path.home() / ".localcoder"
    DB_PATH: Path = BASE_DIR / "localcoder.db"
    VECTOR_DIR: Path = BASE_DIR / "vectors"
    SNAPSHOT_DIR: Path = BASE_DIR / "snapshots"
    LOG_DIR: Path = BASE_DIR / "logs"
    PLUGIN_DIR: Path = BASE_DIR / "plugins"

    # ── LLM ───────────────────────────────────────────────────────────────────
    LLM_PROVIDER: LLMProvider = LLMProvider.OLLAMA
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen2.5-coder:7b"
    LLAMA_CPP_MODEL_PATH: str = ""
    LLM_TEMPERATURE: float = 0.1
    LLM_MAX_TOKENS: int = 4096
    LLM_CONTEXT_WINDOW: int = 32768
    LLM_TIMEOUT: int = 120

    # ── Vector Store ──────────────────────────────────────────────────────────
    VECTOR_STORE: VectorStore = VectorStore.CHROMA
    EMBEDDING_MODEL: str = "nomic-embed-text"
    CHUNK_SIZE: int = 512
    CHUNK_OVERLAP: int = 64
    TOP_K_RESULTS: int = 10

    # ── Agent ─────────────────────────────────────────────────────────────────
    AGENT_MAX_ITERATIONS: int = 20
    AGENT_STEP_TIMEOUT: int = 60
    AGENT_TOTAL_TIMEOUT: int = 600

    # ── Permissions ───────────────────────────────────────────────────────────
    DEFAULT_PERMISSION_LEVEL: int = 1   # 0=read 1=edit 2=delete/install 3=system
    REQUIRE_APPROVAL: bool = True

    # ── Terminal ──────────────────────────────────────────────────────────────
    TERMINAL_TIMEOUT: int = 30
    TERMINAL_MAX_OUTPUT: int = 50_000
    SANDBOX_ENABLED: bool = True

    # ── API ───────────────────────────────────────────────────────────────────
    API_HOST: str = "127.0.0.1"
    API_PORT: int = 8765
    API_RELOAD: bool = False
    CORS_ORIGINS: list[str] = ["http://localhost:1420", "http://localhost:5173"]

    # ── Security ──────────────────────────────────────────────────────────────
    CLOUD_UPLOAD_ENABLED: bool = False
    TELEMETRY_ENABLED: bool = False

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True

    def ensure_dirs(self) -> None:
        """Create all required directories."""
        for d in (
            self.BASE_DIR,
            self.VECTOR_DIR,
            self.SNAPSHOT_DIR,
            self.LOG_DIR,
            self.PLUGIN_DIR,
        ):
            d.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_dirs()
