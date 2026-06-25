"""
LocalCoder Test Configuration.
Provides async fixtures, mock LLM, and temp project directory.
"""

from __future__ import annotations

import asyncio
import shutil
import tempfile
from pathlib import Path
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import AsyncClient

# Make sure the backend package is importable
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture(scope="session")
def event_loop():
    """Use a single event loop for the session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def temp_project(tmp_path: Path) -> Path:
    """Create a temporary project directory with sample files."""
    # Python project structure
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()

    (tmp_path / "src" / "main.py").write_text(
        '"""Main module."""\n\ndef hello(name: str) -> str:\n    return f"Hello, {name}!"\n'
    )
    (tmp_path / "src" / "utils.py").write_text(
        'def add(a: int, b: int) -> int:\n    return a + b\n'
    )
    (tmp_path / "tests" / "test_main.py").write_text(
        'from src.main import hello\n\ndef test_hello():\n    assert hello("world") == "Hello, world!"\n'
    )
    (tmp_path / "requirements.txt").write_text("fastapi\nuvicorn\n")
    (tmp_path / "README.md").write_text("# Test Project\n")

    return tmp_path


@pytest.fixture
def mock_llm():
    """Mock LLM that returns canned responses."""
    llm = MagicMock()
    llm.chat = AsyncMock(return_value="Mock LLM response")
    llm.stream = AsyncMock(return_value=iter(["Mock ", "streamed ", "response"]))
    llm.embed = AsyncMock(return_value=[0.1] * 768)
    llm.is_available = AsyncMock(return_value=True)
    return llm


@pytest.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client for API tests."""
    from backend.api.app import app
    from backend.core.database import init_db

    await init_db()

    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client
