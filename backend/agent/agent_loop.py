"""
LocalCoder — Agent Loop.
States: IDLE → UNDERSTANDING → PLANNING → EXECUTING → VALIDATING → COMPLETED | FAILED
"""

from __future__ import annotations

import asyncio
import json
import traceback
import uuid
from datetime import datetime
from typing import Any, AsyncGenerator, Optional

from backend.core.config import settings
from backend.core.database import execute, fetch_one
from backend.core.llm import get_llm, LLMBase
from backend.core.logging import get_logger
from backend.memory.context_engine import ContextEngine
from backend.memory.memory_manager import MemoryManager
from backend.memory.snapshot_manager import SnapshotManager
from backend.models.types import (
    AgentState, Message, PermissionLevel,
    Plan, PlanStep, TaskRequest, TaskResponse, ToolResult,
)
from backend.tools.file_agent import FileAgent
from backend.tools.git_agent import GitAgent
from backend.tools.repo_intelligence import RepoIntelligence
from backend.tools.terminal_agent import TerminalAgent
from backend.tools.testing_agent import TestingAgent

log = get_logger(__name__)

SYSTEM_PROMPT = """You are LocalCoder, a local-first autonomous AI coding agent.
You have access to file, terminal, git, and testing tools.
Always think step by step. When generating code, produce complete, production-quality output.
Use the project's existing style and conventions.
When asked to fix bugs, first understand the root cause, then fix it properly.
Always verify your changes by running tests when a test suite exists.
Format tool calls as JSON: {"tool": "<name>", "args": {<key>: <value>}}
Available tools: file_read, file_create, file_modify, file_delete, file_list,
terminal_run, git_status, git_diff, git_commit, test_run, repo_scan."""


class AgentLoop:
    """
    Main autonomous agent loop.
    One instance per task execution.
    """

    def __init__(self, task_id: str, request: TaskRequest, llm: Optional[LLMBase] = None) -> None:
        self.task_id     = task_id
        self.request     = request
        self.llm         = llm or get_llm()
        self.project_path = request.project_path or "."
        self.perm_level  = request.permission_level

        # Subsystems
        self.memory    = MemoryManager(task_id)
        self.file_agent = FileAgent(
            self.project_path, task_id, self.perm_level,
            snapshot_dir=str(settings.SNAPSHOT_DIR),
        )
        self.terminal  = TerminalAgent(self.project_path, task_id, self.perm_level)
        self.git        = GitAgent(self.project_path, task_id, self.perm_level)
        self.tester    = TestingAgent(self.project_path, task_id, self.perm_level)
        self.repo      = RepoIntelligence(self.project_path)
        self.context_engine = ContextEngine(self.project_path)
        self.snapshots = SnapshotManager(self.project_path, task_id)

        self._state      = AgentState.IDLE
        self._steps: list[dict] = []
        self._cancelled  = False

    # ── State helpers ─────────────────────────────────────────────────────────

    async def _set_state(self, state: AgentState) -> None:
        self._state = state
        await execute(
            "UPDATE tasks SET status=?, updated_at=? WHERE id=?",
            (state.value, datetime.utcnow().isoformat(), self.task_id),
        )
        log.info("agent.state", task=self.task_id, state=state.value)

    def _add_step(self, name: str, result: ToolResult) -> None:
        self._steps.append({
            "step": name,
            "success": result.success,
            "output": result.output[:500],
            "error": result.error,
        })

    # ── Main entry ────────────────────────────────────────────────────────────

    async def run(self) -> TaskResponse:
        """Execute the full agent loop, returning the final response."""
        start = datetime.utcnow()
        try:
            await self._set_state(AgentState.UNDERSTANDING)
            system_ctx = await self.memory.load_system_context(self.project_path)
            repo_ctx   = await self._understand_repo()

            await self._set_state(AgentState.PLANNING)
            plan = await self._plan(repo_ctx, system_ctx)

            await self._set_state(AgentState.EXECUTING)
            await self._execute(plan)

            await self._set_state(AgentState.VALIDATING)
            validation = await self._validate()

            result_summary = await self._summarize(plan, validation)
            await self.memory.short.persist()

            await self._set_state(AgentState.COMPLETED)
            return await self._build_response(AgentState.COMPLETED, result_summary)

        except asyncio.CancelledError:
            log.warning("agent.cancelled", task=self.task_id)
            await self._set_state(AgentState.FAILED)
            return await self._build_response(AgentState.FAILED, error="Task cancelled")

        except Exception as exc:
            tb = traceback.format_exc()
            log.error("agent.error", task=self.task_id, error=str(exc), traceback=tb)
            await self._set_state(AgentState.FAILED)
            return await self._build_response(AgentState.FAILED, error=str(exc))

    # ── UNDERSTANDING ─────────────────────────────────────────────────────────

    async def _understand_repo(self) -> str:
        """Scan repo and build context."""
        try:
            repo_info = await self.repo.scan(max_files=2000)
            tree = self.repo.build_tree(max_depth=3)
            semantic_ctx = await self.context_engine.get_relevant_context(
                self.request.prompt, max_chars=4000
            )

            summary = (
                f"Project: {self.project_path}\n"
                f"Languages: {', '.join(repo_info.languages.keys())}\n"
                f"Frameworks: {', '.join(repo_info.frameworks)}\n"
                f"Total files: {repo_info.total_files}\n\n"
                f"Directory tree:\n{tree}\n\n"
            )
            if semantic_ctx:
                summary += f"\n{semantic_ctx}"

            self.memory.short.set_context("repo_info", repo_info.dict())
            log.info("agent.understood_repo", files=repo_info.total_files)
            return summary
        except Exception as exc:
            log.warning("agent.repo_scan_failed", error=str(exc))
            return f"Project path: {self.project_path}"

    # ── PLANNING ──────────────────────────────────────────────────────────────

    async def _plan(self, repo_ctx: str, system_ctx: str) -> Plan:
        """Ask LLM to produce a step-by-step plan."""
        self.memory.short.add_message("user", self.request.prompt)

        planning_prompt = (
            f"{system_ctx}\n\n"
            f"Repository context:\n{repo_ctx}\n\n"
            f"Task: {self.request.prompt}\n\n"
            "Create a detailed execution plan. "
            "Respond ONLY with valid JSON in this exact format:\n"
            '{"goal": "<goal>", "reasoning": "<why>", "steps": ['
            '{"step_id": 1, "description": "<what>", "tool": "<tool_name>", '
            '"args": {}, "depends_on": []}'
            "]}"
        )

        messages = [Message(role="user", content=planning_prompt)]
        raw = await self.llm.chat(messages, temperature=0.2, max_tokens=2000)
        self.memory.short.add_message("assistant", raw)

        try:
            # Extract JSON from response
            raw_clean = raw.strip()
            start = raw_clean.find("{")
            end   = raw_clean.rfind("}") + 1
            plan_json = json.loads(raw_clean[start:end])

            steps = [PlanStep(**s) for s in plan_json.get("steps", [])]
            plan = Plan(
                goal=plan_json.get("goal", self.request.prompt),
                steps=steps,
                reasoning=plan_json.get("reasoning", ""),
            )
            log.info("agent.planned", steps=len(steps), goal=plan.goal)
            return plan
        except Exception as exc:
            log.warning("agent.plan_parse_failed", error=str(exc), raw=raw[:200])
            # Fallback: single-step plan
            return Plan(
                goal=self.request.prompt,
                steps=[
                    PlanStep(
                        step_id=1,
                        description="Execute task with LLM guidance",
                        tool="terminal_run",
                        args={"command": "echo 'Starting task'"},
                    )
                ],
            )

    # ── EXECUTING ─────────────────────────────────────────────────────────────

    async def _execute(self, plan: Plan) -> None:
        """Execute plan steps, respecting dependencies."""
        completed: set[int] = set()
        iterations = 0

        for step in plan.steps:
            if iterations >= settings.AGENT_MAX_ITERATIONS:
                log.warning("agent.max_iterations_reached")
                break

            # Wait for dependencies
            for dep in step.depends_on:
                if dep not in completed:
                    log.warning("agent.dependency_not_met", step=step.step_id, dep=dep)

            step.status = "running"
            log.info("agent.executing_step", step=step.step_id, tool=step.tool)

            result = await self._dispatch_tool(step.tool, step.args, step.description)
            self._add_step(step.description, result)

            if result.success:
                step.status = "done"
                completed.add(step.step_id)
            else:
                step.status = "failed"
                # Attempt LLM-guided recovery
                fixed = await self._recover(step, result)
                if fixed:
                    step.status = "done"
                    completed.add(step.step_id)

            iterations += 1

    async def _dispatch_tool(self, tool: str, args: dict, description: str) -> ToolResult:
        """Route tool name to the appropriate agent method."""
        try:
            if tool == "file_read":
                return await self.file_agent.read(args.get("path", ""))
            elif tool == "file_create":
                return await self.file_agent.create(args["path"], args.get("content", ""))
            elif tool == "file_modify":
                return await self.file_agent.modify(args["path"], args.get("content", ""))
            elif tool == "file_delete":
                return await self.file_agent.delete(args["path"])
            elif tool == "file_list":
                return await self.file_agent.list_dir(args.get("path", "."))
            elif tool == "terminal_run":
                return await self.terminal.run(args.get("command", "echo ok"))
            elif tool == "git_status":
                return await self.git.status()
            elif tool == "git_diff":
                return await self.git.diff(args.get("staged", False))
            elif tool == "git_commit":
                msg = args.get("message") or await self.git.generate_commit_message(
                    self.llm, self.file_agent.changed_files
                )
                await self.git.stage()
                return await self.git.commit(msg)
            elif tool == "test_run":
                return await self.tester.run()
            elif tool == "repo_scan":
                info = await self.repo.scan()
                return ToolResult(
                    tool_name="repo_scan",
                    success=True,
                    output=f"Languages: {info.languages}\nFrameworks: {info.frameworks}",
                )
            else:
                # Ask LLM to figure out the right action
                return await self._llm_guided_action(tool, args, description)
        except Exception as exc:
            log.error("agent.dispatch_error", tool=tool, error=str(exc))
            return ToolResult(tool_name=tool, success=False, error=str(exc))

    async def _llm_guided_action(self, tool: str, args: dict, description: str) -> ToolResult:
        """Let the LLM decide what command/code to run for unknown tools."""
        prompt = (
            f"Task: {description}\n"
            f"Tool requested: {tool}\n"
            f"Args: {json.dumps(args)}\n\n"
            "What shell command should I run to accomplish this? "
            "Reply with ONLY the command, no explanation."
        )
        messages = [Message(role="user", content=prompt)]
        cmd = (await self.llm.chat(messages, temperature=0.1)).strip().strip("`")
        return await self.terminal.run(cmd)

    # ── RECOVERY ──────────────────────────────────────────────────────────────

    async def _recover(self, step: PlanStep, failure: ToolResult) -> bool:
        """Ask LLM to suggest a fix and try again."""
        log.info("agent.recovering", step=step.step_id, error=failure.error)

        prompt = (
            f"A step failed.\n"
            f"Description: {step.description}\n"
            f"Tool: {step.tool}\n"
            f"Error: {failure.error}\n"
            f"Output: {failure.output[:1000]}\n\n"
            "Suggest a corrective action as JSON: "
            '{"tool": "<tool>", "args": {<...>}}'
        )
        messages = [Message(role="user", content=prompt)]
        try:
            raw = await self.llm.chat(messages, temperature=0.1)
            start, end = raw.find("{"), raw.rfind("}") + 1
            fix = json.loads(raw[start:end])
            result = await self._dispatch_tool(fix["tool"], fix.get("args", {}), "recovery")
            return result.success
        except Exception as exc:
            log.warning("agent.recovery_failed", error=str(exc))
            return False

    # ── VALIDATING ────────────────────────────────────────────────────────────

    async def _validate(self) -> str:
        """Run tests if available, return validation summary."""
        fw = self.tester.detect_framework()
        if fw is None:
            return "No test suite detected; skipping validation."

        log.info("agent.validating")
        result = await self.tester.run(fw)
        self._add_step("Run tests", result)

        if result.success:
            return "All tests passed ✓"

        # Attempt test-fix loop (max 2 retries)
        for attempt in range(2):
            log.info("agent.test_fix_attempt", attempt=attempt + 1)
            fix_suggestion = await self.tester.analyze_and_fix_prompt(result.output, self.llm)
            self.memory.short.add_message("assistant", fix_suggestion)
            # Re-run
            result = await self.tester.run(fw)
            if result.success:
                return f"Tests fixed and passing after {attempt + 1} attempt(s) ✓"

        return f"Tests still failing after fix attempts. Output:\n{result.output[:500]}"

    # ── SUMMARIZE ─────────────────────────────────────────────────────────────

    async def _summarize(self, plan: Plan, validation: str) -> str:
        """Ask LLM to write a concise result summary."""
        steps_summary = "\n".join(
            f"- [{s['step']}]: {'✓' if s['success'] else '✗'} {s.get('error','')}"
            for s in self._steps
        )
        prompt = (
            f"Task: {self.request.prompt}\n"
            f"Plan goal: {plan.goal}\n"
            f"Steps executed:\n{steps_summary}\n"
            f"Validation: {validation}\n\n"
            "Write a concise summary of what was accomplished (2-4 sentences)."
        )
        messages = [Message(role="user", content=prompt)]
        return await self.llm.chat(messages, temperature=0.2, max_tokens=300)

    # ── Response builder ──────────────────────────────────────────────────────

    async def _build_response(
        self, state: AgentState, result: str = "", error: str = ""
    ) -> TaskResponse:
        steps_json = json.dumps(self._steps)
        changed = len(self.file_agent.changed_files)

        await execute(
            """UPDATE tasks SET status=?, result=?, error=?, files_changed=?, steps=?, updated_at=?
               WHERE id=?""",
            (state.value, result, error, changed, steps_json, datetime.utcnow().isoformat(), self.task_id),
        )
        return TaskResponse(
            task_id=self.task_id,
            status=state,
            result=result or None,
            error=error or None,
            files_changed=changed,
            steps=self._steps,
        )

    def cancel(self) -> None:
        self._cancelled = True
