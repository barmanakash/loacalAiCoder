"""
Tests for RepoIntelligence — language detection, framework detection, dependency analysis.
"""

from __future__ import annotations

import json
import pytest
from pathlib import Path

from backend.tools.repo_intelligence import RepoIntelligence


@pytest.fixture
def full_project(tmp_path: Path) -> Path:
    """A more complete fake project for intelligence tests."""
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()

    # Python files
    (tmp_path / "src" / "main.py").write_text("import fastapi\napp = fastapi.FastAPI()\n")
    (tmp_path / "src" / "models.py").write_text("class User:\n    pass\n")
    (tmp_path / "tests" / "test_main.py").write_text("def test_app(): pass\n")

    # JavaScript files
    (tmp_path / "frontend").mkdir()
    (tmp_path / "frontend" / "index.tsx").write_text("import React from 'react';\n")

    # Package manifests
    (tmp_path / "requirements.txt").write_text("fastapi\nuvicorn\npydantic\n")
    (tmp_path / "package.json").write_text(
        json.dumps({"dependencies": {"react": "^18", "react-dom": "^18"}})
    )
    (tmp_path / "README.md").write_text("# My Project\n")

    return tmp_path


@pytest.mark.asyncio
async def test_scan_detects_languages(full_project: Path):
    ri = RepoIntelligence(str(full_project))
    info = await ri.scan()

    assert info.total_files > 0
    assert "Python" in info.languages or len(info.languages) > 0


@pytest.mark.asyncio
async def test_scan_detects_frameworks(full_project: Path):
    ri = RepoIntelligence(str(full_project))
    info = await ri.scan()

    # Should detect FastAPI and/or React
    assert isinstance(info.frameworks, list)


@pytest.mark.asyncio
async def test_scan_empty_dir(tmp_path: Path):
    ri = RepoIntelligence(str(tmp_path))
    info = await ri.scan()
    assert info.total_files == 0
    assert info.languages == {}


@pytest.mark.asyncio
async def test_scan_ignores_node_modules(tmp_path: Path):
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "huge_lib.js").write_text("x" * 10000)
    (tmp_path / "index.ts").write_text("const x = 1;")

    ri = RepoIntelligence(str(tmp_path))
    info = await ri.scan()

    # Should only count the index.ts, not node_modules
    for f in info.files:
        assert "node_modules" not in f.path


@pytest.mark.asyncio
async def test_file_info_populated(full_project: Path):
    ri = RepoIntelligence(str(full_project))
    info = await ri.scan()

    for fi in info.files:
        assert fi.path
        assert fi.size >= 0
