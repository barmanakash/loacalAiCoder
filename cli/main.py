#!/usr/bin/env python3
"""
LocalCoder CLI.

Commands:
  localcoder chat              — interactive chat with the agent
  localcoder run "<task>"      — run a one-shot task
  localcoder review            — review recent changes
  localcoder init              — initialise LocalCoder in a project
  localcoder tasks             — list recent tasks
  localcoder rollback <id>     — rollback a task's file changes
  localcoder index             — index the current repo
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Optional

import click
import httpx
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.syntax import Syntax
from rich.table import Table

console = Console()
API_BASE = os.environ.get("LOCALCODER_API", "http://127.0.0.1:8765")


def api(path: str) -> str:
    return f"{API_BASE}{path}"


# ── Helpers ───────────────────────────────────────────────────────────────────

def check_server() -> bool:
    try:
        r = httpx.get(api("/api/health"), timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def run_task_sync(prompt: str, project_path: str, permission: int) -> dict:
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]{task.description}"),
        transient=True,
    ) as prog:
        prog.add_task("Agent thinking...", total=None)
        r = httpx.post(
            api("/api/agent/task"),
            json={
                "prompt": prompt,
                "project_path": project_path,
                "permission_level": permission,
            },
            timeout=600,
        )
    r.raise_for_status()
    return r.json()


# ── CLI Group ─────────────────────────────────────────────────────────────────

@click.group()
@click.version_option("1.0.0", prog_name="LocalCoder")
def cli():
    """LocalCoder AI Agent — local-first autonomous coding assistant."""


# ── init ──────────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("path", default=".", type=click.Path())
def init(path: str):
    """Initialise LocalCoder in a project directory."""
    project = Path(path).resolve()
    config_file = project / ".localcoder.toml"

    if config_file.exists():
        console.print(f"[yellow]Already initialised:[/] {config_file}")
        return

    config_content = f"""# LocalCoder project configuration
[project]
name = "{project.name}"
description = ""

[agent]
permission_level = 1   # 0=read 1=edit 2=destructive 3=system
max_iterations = 20

[llm]
model = "qwen2.5-coder:7b"
temperature = 0.1
"""
    config_file.write_text(config_content)
    console.print(
        Panel(
            f"[green]✓ LocalCoder initialised[/]\n\n"
            f"Project: [bold]{project.name}[/]\n"
            f"Config:  {config_file}",
            title="LocalCoder Init",
        )
    )


# ── run ───────────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("task")
@click.option("--path", "-p", default=".", help="Project directory")
@click.option("--permission", "-P", default=1, type=int, help="Permission level (0-3)")
def run(task: str, path: str, permission: int):
    """Run a one-shot task."""
    if not check_server():
        console.print("[red]LocalCoder server not running.[/] Start with: uvicorn backend.api.app:app")
        sys.exit(1)

    console.print(Panel(f"[bold]{task}[/]", title="[cyan]Task[/]"))
    project_path = str(Path(path).resolve())

    try:
        result = run_task_sync(task, project_path, permission)
    except httpx.HTTPError as e:
        console.print(f"[red]API error:[/] {e}")
        sys.exit(1)

    status = result.get("status", "UNKNOWN")
    colour = "green" if status == "COMPLETED" else "red"

    console.print(Panel(
        f"[{colour}]Status: {status}[/]\n\n"
        + (result.get("result") or result.get("error") or ""),
        title="Result",
    ))

    if result.get("files_changed"):
        console.print(f"[dim]Files changed: {result['files_changed']}[/]")

    # Show steps
    steps = result.get("steps", [])
    if steps:
        table = Table(title="Steps", show_lines=True)
        table.add_column("Step", style="bold")
        table.add_column("Status")
        table.add_column("Output")
        for s in steps:
            icon = "✓" if s.get("success") else "✗"
            colour = "green" if s.get("success") else "red"
            table.add_row(
                s.get("step", ""),
                f"[{colour}]{icon}[/{colour}]",
                (s.get("output") or s.get("error") or "")[:80],
            )
        console.print(table)


# ── chat ──────────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--path", "-p", default=".", help="Project directory")
def chat(path: str):
    """Interactive chat with the agent."""
    if not check_server():
        console.print("[red]LocalCoder server not running.[/]")
        sys.exit(1)

    project_path = str(Path(path).resolve())
    console.print(Panel(
        f"[bold cyan]LocalCoder Chat[/]\n"
        f"Project: {project_path}\n"
        "Type [bold]exit[/] to quit.",
        title="LocalCoder",
    ))

    while True:
        try:
            user_input = console.input("\n[bold green]You >[/] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye.[/]")
            break

        if user_input.lower() in ("exit", "quit", "q"):
            break
        if not user_input:
            continue

        try:
            result = run_task_sync(user_input, project_path, 1)
            content = result.get("result") or result.get("error") or ""
            console.print(Markdown(content))
        except Exception as e:
            console.print(f"[red]Error:[/] {e}")


# ── review ────────────────────────────────────────────────────────────────────

@cli.command()
def review():
    """Review recent agent activity."""
    if not check_server():
        console.print("[red]Server not running.[/]")
        sys.exit(1)

    r = httpx.get(api("/api/agent/tasks"), timeout=10)
    r.raise_for_status()
    tasks = r.json()

    table = Table(title="Recent Tasks", show_lines=True)
    table.add_column("ID", style="dim", width=8)
    table.add_column("Prompt")
    table.add_column("Status")
    table.add_column("Files")
    table.add_column("Created")

    for t in tasks:
        status = t.get("status", "")
        colour = "green" if status == "COMPLETED" else "red" if status == "FAILED" else "yellow"
        table.add_row(
            t["id"][:8],
            (t.get("prompt") or "")[:50],
            f"[{colour}]{status}[/{colour}]",
            str(t.get("files_changed", 0)),
            t.get("created_at", "")[:19],
        )

    console.print(table)


# ── tasks ─────────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--status", default=None)
@click.option("--limit", default=20, type=int)
def tasks(status: Optional[str], limit: int):
    """List tasks."""
    if not check_server():
        console.print("[red]Server not running.[/]")
        sys.exit(1)

    params = {"limit": limit}
    if status:
        params["status"] = status.upper()

    r = httpx.get(api("/api/agent/tasks"), params=params, timeout=10)
    r.raise_for_status()

    for t in r.json():
        colour = {"COMPLETED": "green", "FAILED": "red"}.get(t.get("status"), "yellow")
        console.print(
            f"[dim]{t['id'][:8]}[/] [{colour}]{t['status']:12}[/{colour}] "
            f"{(t.get('prompt') or '')[:60]}"
        )


# ── rollback ──────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("task_id")
@click.option("--path", "-p", default=".", help="Project directory")
def rollback(task_id: str, path: str):
    """Rollback all file changes from a task."""
    console.print(f"[yellow]Rolling back task {task_id[:8]}...[/]")
    # The rollback is handled by the SnapshotManager on the server
    r = httpx.post(
        api(f"/api/agent/task/{task_id}/rollback"),
        json={"path": path},
        timeout=30,
    )
    if r.status_code == 404:
        console.print("[red]Task not found.[/]")
        return
    data = r.json()
    console.print(f"[green]Restored {len(data.get('restored', []))} files.[/]")


# ── index ─────────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--path", "-p", default=".", help="Project directory")
def index(path: str):
    """Index the repository for semantic search."""
    if not check_server():
        console.print("[red]Server not running.[/]")
        sys.exit(1)

    project_path = str(Path(path).resolve())
    console.print(f"[cyan]Indexing {project_path}...[/]")

    with Progress(SpinnerColumn(), TextColumn("{task.description}"), transient=True) as prog:
        prog.add_task("Embedding files...", total=None)
        r = httpx.post(api("/api/repo/index"), json={"path": project_path}, timeout=300)

    r.raise_for_status()
    data = r.json()
    console.print(f"[green]Indexed {data['indexed_chunks']} chunks.[/]")


if __name__ == "__main__":
    cli()
