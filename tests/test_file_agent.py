"""
Tests for FileAgent — read, create, modify, delete, rollback, diff.
"""

from __future__ import annotations

import pytest
from pathlib import Path

from backend.models.types import PermissionLevel
from backend.tools.file_agent import FileAgent


@pytest.fixture
def agent(temp_project: Path) -> FileAgent:
    return FileAgent(
        project_root=str(temp_project),
        task_id="test-task-001",
        permission_level=PermissionLevel.DESTRUCTIVE,
        snapshot_dir=str(temp_project / ".snapshots"),
    )


@pytest.mark.asyncio
async def test_read_existing_file(agent: FileAgent, temp_project: Path):
    result = await agent.read("src/main.py")
    assert result.success
    assert "hello" in result.output
    assert result.metadata["lines"] > 0


@pytest.mark.asyncio
async def test_read_missing_file(agent: FileAgent):
    result = await agent.read("nonexistent.py")
    assert not result.success
    assert "not found" in result.error.lower()


@pytest.mark.asyncio
async def test_create_file(agent: FileAgent, temp_project: Path):
    result = await agent.create("src/new_module.py", "def greet(): return 'hi'\n")
    assert result.success
    assert (temp_project / "src" / "new_module.py").exists()


@pytest.mark.asyncio
async def test_create_file_creates_dirs(agent: FileAgent, temp_project: Path):
    result = await agent.create("deep/nested/file.py", "x = 1\n")
    assert result.success
    assert (temp_project / "deep" / "nested" / "file.py").exists()


@pytest.mark.asyncio
async def test_modify_file(agent: FileAgent, temp_project: Path):
    new_content = "def hello(name):\n    return f'Hi {name}'\n"
    result = await agent.modify("src/main.py", new_content)
    assert result.success
    assert (temp_project / "src" / "main.py").read_text() == new_content


@pytest.mark.asyncio
async def test_modify_produces_diff(agent: FileAgent):
    result = await agent.modify("src/main.py", "# changed\n")
    assert result.success
    assert "@@" in result.output or "---" in result.output or result.metadata.get("diff", "")


@pytest.mark.asyncio
async def test_path_escape_blocked(agent: FileAgent):
    with pytest.raises(PermissionError):
        await agent.read("../../etc/passwd")


@pytest.mark.asyncio
async def test_list_dir(agent: FileAgent):
    result = await agent.list_dir("src")
    assert result.success
    assert "main.py" in result.output


@pytest.mark.asyncio
async def test_delete_file(agent: FileAgent, temp_project: Path):
    path = temp_project / "src" / "utils.py"
    assert path.exists()
    result = await agent.delete("src/utils.py")
    assert result.success
    assert not path.exists()


@pytest.mark.asyncio
async def test_diff_shows_changes(agent: FileAgent):
    result = await agent.diff("src/main.py", "# completely different\n")
    assert result.success
    assert result.output  # should have diff output


@pytest.mark.asyncio
async def test_changed_files_tracked(agent: FileAgent, temp_project: Path):
    await agent.create("new1.py", "x = 1")
    await agent.create("new2.py", "y = 2")
    assert len(agent.changed_files) == 2
