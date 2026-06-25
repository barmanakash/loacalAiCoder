"""
Integration tests for the LocalCoder FastAPI endpoints.
Uses an in-memory test client — no real LLM required.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch
from pathlib import Path


@pytest.mark.asyncio
async def test_health_endpoint(async_client):
    """Health check should always respond."""
    with patch("backend.core.llm.get_llm") as mock_llm_factory:
        mock_llm = AsyncMock()
        mock_llm.is_available = AsyncMock(return_value=True)
        mock_llm_factory.return_value = mock_llm

        resp = await async_client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert "version" in data


@pytest.mark.asyncio
async def test_list_tasks_empty(async_client):
    """Listing tasks on a fresh DB should return empty list."""
    resp = await async_client.get("/api/agent/tasks")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_scan_repo(async_client, temp_project: Path):
    """Repository scanning should return project info."""
    resp = await async_client.post(
        "/api/repo/scan",
        json={"path": str(temp_project)},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "total_files" in data
    assert data["total_files"] > 0


@pytest.mark.asyncio
async def test_llm_info_endpoint(async_client):
    """LLM info endpoint should return config details."""
    resp = await async_client.get("/api/llm/info")
    assert resp.status_code == 200
    data = resp.json()
    assert "provider" in data
    assert "model" in data


@pytest.mark.asyncio
async def test_memory_set_and_get(async_client):
    """Memory set/get roundtrip."""
    key = "test_key_123"
    value = {"test": True, "count": 42}

    resp = await async_client.post(
        "/api/memory/set",
        json={"key": key, "value": value, "category": "test"},
    )
    assert resp.status_code == 200

    resp = await async_client.get(f"/api/memory/{key}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["key"] == key
    assert data["value"] == value


@pytest.mark.asyncio
async def test_task_not_found(async_client):
    """Fetching a non-existent task should 404."""
    resp = await async_client.get("/api/agent/task/nonexistent-id")
    assert resp.status_code == 404
