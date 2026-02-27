"""
FastAPI integration tests for the /story and /text2sprite routers.

The tests use httpx.AsyncClient against the FastAPI app directly (no
running server needed) so they are safe to run in CI without GPU hardware.
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from ai_services.main import app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture()
async def client():
    """Async HTTP client wired directly to the FastAPI app."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


# ---------------------------------------------------------------------------
# /story
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_story_generate_returns_job_id(client):
    resp = await client.post(
        "/story/generate",
        json={"player_input": "move north", "world_state_id": "00001"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "job_id" in data
    assert data["status"] == "queued"


@pytest.mark.asyncio
async def test_story_status_unknown_job(client):
    resp = await client.get("/story/status/nonexistent_job_id")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_story_status_known_job(client):
    # Submit then immediately poll – job will be queued (worker not running).
    post = await client.post(
        "/story/generate",
        json={"player_input": "look around"},
    )
    job_id = post.json()["job_id"]

    get = await client.get(f"/story/status/{job_id}")
    assert get.status_code == 200
    data = get.json()
    assert data["job_id"] == job_id
    assert data["status"] in ("queued", "running", "done", "error")


# ---------------------------------------------------------------------------
# /text2sprite
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sprite_generate_returns_job_id(client):
    resp = await client.post(
        "/text2sprite/generate",
        json={"player_input": "a green slime", "world_state_id": "00001"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "job_id" in data
    assert data["status"] == "queued"


@pytest.mark.asyncio
async def test_sprite_status_unknown_job(client):
    resp = await client.get("/text2sprite/status/nonexistent_job_id")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_sprite_status_known_job(client):
    post = await client.post(
        "/text2sprite/generate",
        json={"player_input": "a knight"},
    )
    job_id = post.json()["job_id"]

    get = await client.get(f"/text2sprite/status/{job_id}")
    assert get.status_code == 200
    data = get.json()
    assert data["job_id"] == job_id
    assert data["status"] in ("queued", "running", "done", "error")
