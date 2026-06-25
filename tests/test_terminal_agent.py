"""
Tests for TerminalAgent — command execution, timeout, blocking.
"""

from __future__ import annotations

import pytest
from pathlib import Path

from backend.models.types import PermissionLevel
from backend.tools.terminal_agent import TerminalAgent


@pytest.fixture
def agent(temp_project: Path) -> TerminalAgent:
    return TerminalAgent(
        cwd=str(temp_project),
        task_id="test-task-002",
        permission_level=PermissionLevel.EDIT,
    )


@pytest.mark.asyncio
async def test_run_basic_command(agent: TerminalAgent):
    result = await agent.run("echo hello")
    assert result.success
    assert "hello" in result.output


@pytest.mark.asyncio
async def test_run_failing_command(agent: TerminalAgent):
    result = await agent.run("exit 1")
    assert not result.success
    assert result.metadata["exit_code"] == 1


@pytest.mark.asyncio
async def test_command_timeout(agent: TerminalAgent):
    result = await agent.run("sleep 60", timeout=1)
    assert not result.success
    assert "timed out" in result.error.lower()


@pytest.mark.asyncio
async def test_blocked_dangerous_command(agent: TerminalAgent):
    """rm -rf / should be blocked outright."""
    result = await agent.run("rm -rf /")
    assert not result.success
    assert "blocked" in result.error.lower()


@pytest.mark.asyncio
async def test_which_python(agent: TerminalAgent):
    """Python should be available in the test environment."""
    available = await agent.which("python3")
    assert isinstance(available, bool)


@pytest.mark.asyncio
async def test_history_tracked(agent: TerminalAgent):
    await agent.run("echo one")
    await agent.run("echo two")
    assert len(agent.history) == 2
    assert agent.history[0]["command"] == "echo one"


@pytest.mark.asyncio
async def test_run_python_script(agent: TerminalAgent, temp_project: Path):
    script = temp_project / "script.py"
    script.write_text("print('LocalCoder test')\n")
    result = await agent.run("python3 script.py")
    assert result.success
    assert "LocalCoder test" in result.output
