"""
LocalCoder — Testing Agent.
Detect test framework, run tests, analyze failures, fix and retry.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from backend.core.logging import get_logger
from backend.models.types import PermissionLevel, ToolResult
from backend.tools.terminal_agent import TerminalAgent

log = get_logger(__name__)


class TestFramework:
    name: str
    command: str
    file_patterns: list[str]

    def __init__(self, name: str, command: str, patterns: list[str]) -> None:
        self.name = name
        self.command = command
        self.file_patterns = patterns


FRAMEWORKS = [
    TestFramework("pytest",  "python -m pytest -v --tb=short", ["test_*.py", "*_test.py"]),
    TestFramework("unittest", "python -m unittest discover -v", ["test_*.py"]),
    TestFramework("jest",    "npx jest --no-coverage",         ["*.test.js", "*.test.ts", "*.spec.js", "*.spec.ts"]),
    TestFramework("vitest",  "npx vitest run",                 ["*.test.ts", "*.spec.ts"]),
    TestFramework("cargo",   "cargo test",                     ["*tests*"]),
    TestFramework("go test", "go test ./...",                  ["*_test.go"]),
    TestFramework("rspec",   "bundle exec rspec",              ["*_spec.rb"]),
    TestFramework("phpunit", "vendor/bin/phpunit",             ["*Test.php"]),
]


class TestingAgent:
    def __init__(
        self,
        project_root: str,
        task_id: str,
        permission_level: PermissionLevel = PermissionLevel.EDIT,
    ) -> None:
        self.root = Path(project_root).resolve()
        self.task_id = task_id
        self._terminal = TerminalAgent(
            cwd=str(self.root),
            task_id=task_id,
            permission_level=permission_level,
        )

    def detect_framework(self) -> Optional[TestFramework]:
        """Detect the test framework used in this project."""
        for fw in FRAMEWORKS:
            for pattern in fw.file_patterns:
                if list(self.root.rglob(pattern)):
                    log.info("testing.framework_detected", framework=fw.name)
                    return fw

        # Fallback: check config files
        if (self.root / "pytest.ini").exists() or (self.root / "pyproject.toml").exists():
            return FRAMEWORKS[0]  # pytest
        if (self.root / "jest.config.js").exists() or (self.root / "jest.config.ts").exists():
            return FRAMEWORKS[2]  # jest

        return None

    async def run(self, framework: Optional[TestFramework] = None, extra_args: str = "") -> ToolResult:
        """Run the test suite."""
        fw = framework or self.detect_framework()
        if fw is None:
            return ToolResult(
                tool_name="test_run",
                success=False,
                error="No test framework detected.",
            )

        cmd = fw.command
        if extra_args:
            cmd += " " + extra_args

        log.info("testing.run", framework=fw.name, command=cmd)
        result = await self._terminal.run(cmd, timeout=120)
        failures = self._parse_failures(result.output)

        return ToolResult(
            tool_name="test_run",
            success=result.success,
            output=result.output,
            error=result.error,
            metadata={
                "framework": fw.name,
                "passed": result.success,
                "failures": failures,
            },
        )

    async def run_file(self, test_file: str) -> ToolResult:
        """Run a specific test file."""
        fw = self.detect_framework()
        if fw is None:
            return ToolResult(tool_name="test_run_file", success=False, error="No framework")

        if fw.name == "pytest":
            cmd = f"python -m pytest {test_file} -v --tb=short"
        elif fw.name == "jest":
            cmd = f"npx jest {test_file} --no-coverage"
        else:
            cmd = f"{fw.command} {test_file}"

        return await self._terminal.run(cmd, timeout=60)

    def _parse_failures(self, output: str) -> list[dict]:
        """Extract failing test names and error messages from output."""
        failures = []

        # pytest style
        for m in re.finditer(r"FAILED ([\w/.:]+) - (.+)", output):
            failures.append({"test": m.group(1), "reason": m.group(2).strip()})

        # jest style
        for m in re.finditer(r"✕ (.+?) \((\d+) ms\)", output):
            failures.append({"test": m.group(1).strip(), "reason": "See output"})

        # Generic FAIL pattern
        if not failures:
            for line in output.splitlines():
                if re.match(r"\s*(FAIL|ERROR|FAILED)\b", line):
                    failures.append({"test": line.strip(), "reason": ""})

        return failures

    async def analyze_and_fix_prompt(self, output: str, llm) -> str:
        """Ask LLM for a fix based on test output."""
        from backend.models.types import Message
        messages = [
            Message(
                role="user",
                content=(
                    "The following tests are failing. Analyze the output and suggest "
                    "code fixes. Be specific about which files and lines need to change.\n\n"
                    f"Test output:\n{output[:3000]}"
                ),
            )
        ]
        return await llm.chat(messages, temperature=0.2)
