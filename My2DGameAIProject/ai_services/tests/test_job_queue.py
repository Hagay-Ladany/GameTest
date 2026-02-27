"""
Tests for the async job queue (ai_services/job_queue.py).
"""
from __future__ import annotations

import asyncio
import pytest

from ai_services.job_queue import InferenceQueue, JobStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _echo_worker(params: dict) -> dict:
    """Simple worker that echoes its params back as the result."""
    return {"echo": params.get("value")}


async def _failing_worker(params: dict) -> dict:
    raise RuntimeError("deliberate failure")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_submit_returns_job_id():
    queue = InferenceQueue(worker_fn=_echo_worker)
    job_id = queue.submit({"value": "hello"})
    assert job_id.startswith("job_")


@pytest.mark.asyncio
async def test_job_is_queued_immediately():
    queue = InferenceQueue(worker_fn=_echo_worker)
    job_id = queue.submit({"value": "test"})
    record = queue.get_status(job_id)
    assert record is not None
    assert record["status"] == JobStatus.QUEUED


@pytest.mark.asyncio
async def test_worker_completes_job():
    queue = InferenceQueue(worker_fn=_echo_worker)
    job_id = queue.submit({"value": "world"})

    # Run the worker for exactly one iteration.
    worker_task = asyncio.create_task(queue.run_worker())
    await asyncio.sleep(0.05)
    worker_task.cancel()

    record = queue.get_status(job_id)
    assert record["status"] == JobStatus.DONE
    assert record["result"] == {"echo": "world"}


@pytest.mark.asyncio
async def test_worker_marks_failed_job():
    queue = InferenceQueue(worker_fn=_failing_worker)
    job_id = queue.submit({})

    worker_task = asyncio.create_task(queue.run_worker())
    await asyncio.sleep(0.05)
    worker_task.cancel()

    record = queue.get_status(job_id)
    assert record["status"] == JobStatus.ERROR
    assert "deliberate failure" in record["error"]


@pytest.mark.asyncio
async def test_get_status_unknown_job_returns_none():
    queue = InferenceQueue(worker_fn=_echo_worker)
    assert queue.get_status("nonexistent") is None
