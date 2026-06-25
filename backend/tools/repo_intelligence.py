"""
LocalCoder — Repository Intelligence.
File scanning, language detection, framework detection, dependency analysis, project mapping.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

import aiofiles

from backend.core.logging import get_logger
from backend.models.types import FileInfo, RepoInfo

log = get_logger(__name__)

IGNORE_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "__pycache__", ".pytest_cache",
    "venv", ".venv", "env", ".env", "dist", "build", ".next", ".nuxt",
    "target", "bin", "obj", ".idea", ".vscode", "coverage", ".nyc_output",
}

LANG_MAP: dict[str, str] = {
    ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
    ".tsx": "TypeScript", ".jsx": "JavaScript", ".go": "Go",
    ".rs": "Rust", ".java": "Java", ".kt": "Kotlin", ".rb": "Ruby",
    ".php": "PHP", ".swift": "Swift", ".dart": "Dart", ".lua": "Lua",
    ".r": "R", ".c": "C", ".cpp": "C++", ".h": "C/C++", ".hpp": "C++",
    ".cs": "C#", ".fs": "F#", ".ex": "Elixir", ".exs": "Elixir",
    ".hs": "Haskell", ".scala": "Scala", ".clj": "Clojure",
    ".html": "HTML", ".css": "CSS", ".scss": "SCSS", ".sass": "SASS",
    ".sql": "SQL", ".sh": "Shell", ".bash": "Shell", ".zsh": "Shell",
    ".yaml": "YAML", ".yml": "YAML", ".json": "JSON", ".toml": "TOML",
    ".md": "Markdown", ".rst": "reStructuredText",
}

FRAMEWORK_SIGNALS: dict[str, list[str]] = {
    "React":       ["react", "react-dom", "jsx", "tsx"],
    "Vue":         ["vue", "@vue"],
    "Angular":     ["@angular/core"],
    "Svelte":      ["svelte"],
    "Next.js":     ["next"],
    "Nuxt":        ["nuxt"],
    "FastAPI":     ["fastapi"],
    "Flask":       ["flask"],
    "Django":      ["django"],
    "Express":     ["express"],
    "NestJS":      ["@nestjs/core"],
    "Spring":      ["spring-boot"],
    "Rails":       ["rails"],
    "Laravel":     ["laravel"],
    "Tauri":       ["tauri", "@tauri-apps"],
    "Electron":    ["electron"],
    "PyTorch":     ["torch"],
    "TensorFlow":  ["tensorflow"],
    "LangChain":   ["langchain"],
}


class RepoIntelligence:
    def __init__(self, root: str) -> None:
        self.root = Path(root).resolve()

    def _should_skip(self, p: Path) -> bool:
        return any(part in IGNORE_DIRS for part in p.parts)

    async def scan(self, max_files: int = 5000) -> RepoInfo:
        """Walk the repo and collect stats."""
        lang_counts: dict[str, int] = {}
        files: list[FileInfo] = []
        total_lines = 0

        for path in self.root.rglob("*"):
            if len(files) >= max_files:
                break
            if self._should_skip(path.relative_to(self.root)):
                continue
            if not path.is_file():
                continue

            lang = LANG_MAP.get(path.suffix.lower())
            if lang:
                lang_counts[lang] = lang_counts.get(lang, 0) + 1

            try:
                size = path.stat().st_size
                lines = 0
                if size < 500_000:
                    async with aiofiles.open(path, encoding="utf-8", errors="ignore") as f:
                        content = await f.read()
                    lines = content.count("\n") + 1
                    total_lines += lines

                rel = str(path.relative_to(self.root))
                files.append(FileInfo(path=rel, language=lang, size=size, lines=lines))
            except Exception:
                pass

        frameworks = await self._detect_frameworks()

        info = RepoInfo(
            root=str(self.root),
            languages=lang_counts,
            frameworks=frameworks,
            dependencies=await self._collect_deps(),
            files=files,
            total_files=len(files),
            total_lines=total_lines,
        )
        log.info("repo.scanned", files=len(files), languages=list(lang_counts.keys()))
        return info

    async def _detect_frameworks(self) -> list[str]:
        detected: list[str] = []

        # Check package.json
        pkg_json = self.root / "package.json"
        if pkg_json.exists():
            try:
                async with aiofiles.open(pkg_json, encoding="utf-8") as f:
                    pkg = json.loads(await f.read())
                all_deps = {
                    **pkg.get("dependencies", {}),
                    **pkg.get("devDependencies", {}),
                }
                for fw, signals in FRAMEWORK_SIGNALS.items():
                    if any(s in all_deps for s in signals):
                        detected.append(fw)
            except Exception:
                pass

        # Check requirements.txt / pyproject.toml / setup.py
        for req_file in ("requirements.txt", "requirements-dev.txt"):
            req_path = self.root / req_file
            if req_path.exists():
                try:
                    async with aiofiles.open(req_path, encoding="utf-8") as f:
                        content = (await f.read()).lower()
                    for fw, signals in FRAMEWORK_SIGNALS.items():
                        if any(s.lower() in content for s in signals):
                            detected.append(fw)
                except Exception:
                    pass

        # Detect Tauri
        if (self.root / "src-tauri").exists():
            detected.append("Tauri")

        return list(dict.fromkeys(detected))  # dedup, preserve order

    async def _collect_deps(self) -> dict[str, list[str]]:
        deps: dict[str, list[str]] = {}

        # Python
        req_path = self.root / "requirements.txt"
        if req_path.exists():
            async with aiofiles.open(req_path, encoding="utf-8") as f:
                lines = (await f.read()).splitlines()
            deps["python"] = [
                l.strip().split("==")[0].split(">=")[0]
                for l in lines
                if l.strip() and not l.startswith("#")
            ]

        # Node
        pkg_json = self.root / "package.json"
        if pkg_json.exists():
            try:
                async with aiofiles.open(pkg_json, encoding="utf-8") as f:
                    pkg = json.loads(await f.read())
                deps["node"] = list(pkg.get("dependencies", {}).keys())
            except Exception:
                pass

        return deps

    async def get_file_summary(self, path: str, max_chars: int = 2000) -> str:
        """Return a summarized view of a file for context."""
        p = (self.root / path).resolve()
        try:
            async with aiofiles.open(p, encoding="utf-8", errors="replace") as f:
                content = await f.read()
            if len(content) > max_chars:
                return content[:max_chars] + f"\n... [{len(content) - max_chars} chars truncated]"
            return content
        except Exception as exc:
            return f"[Error reading {path}: {exc}]"

    def build_tree(self, max_depth: int = 4) -> str:
        """Return an ASCII directory tree."""
        lines: list[str] = [str(self.root.name) + "/"]

        def _walk(directory: Path, prefix: str, depth: int) -> None:
            if depth > max_depth:
                return
            try:
                entries = sorted(
                    [e for e in directory.iterdir() if not self._should_skip(e.relative_to(self.root))],
                    key=lambda e: (e.is_file(), e.name.lower()),
                )
            except PermissionError:
                return

            for i, entry in enumerate(entries):
                connector = "└── " if i == len(entries) - 1 else "├── "
                lines.append(f"{prefix}{connector}{entry.name}{'/' if entry.is_dir() else ''}")
                if entry.is_dir():
                    extension = "    " if i == len(entries) - 1 else "│   "
                    _walk(entry, prefix + extension, depth + 1)

        _walk(self.root, "", 1)
        return "\n".join(lines)
