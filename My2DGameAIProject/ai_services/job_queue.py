"""
Async Job Queue
===============
Single-instance asyncio.Queue + in-memory dictionary for AI inference jobs.

Workflow:
  1. A POST endpoint enqueues work and returns a unique job_id immediately.
  2. A background worker coroutine drains the queue and updates job state.
  3. The client polls GET /*/status/{job_id} until status is "done" or "error".

Limitations (by design – use Celery + Redis for production):
  • All state is in-process; jobs are lost on restart.
  • Single worker coroutine per queue (no parallelism within one queue).
"""
from __future__ import annotations

import asyncio
import uuid
from enum import Enum
from typing import Any, Callable, Coroutine


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"


class JobRecord:
    """Holds the mutable state of a single inference job."""

    def __init__(self, job_id: str, params: dict) -> None:
        self.job_id = job_id
        self.params = params
        self.status: JobStatus = JobStatus.QUEUED
        self.result: Any = None
        self.error: str | None = None

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "status": self.status,
            "result": self.result,
            "error": self.error,
        }


class InferenceQueue:
    """
    Wraps an asyncio.Queue and an in-memory job registry.

    Parameters
    ----------
    worker_fn:
        An async callable ``(params: dict) -> Any`` that performs the heavy
        inference work.  It is called for each job dequeued by the background
        worker.
    """

    def __init__(self, worker_fn: Callable[[dict], Coroutine]) -> None:
        self._queue: asyncio.Queue[JobRecord] = asyncio.Queue()
        self._jobs: dict[str, JobRecord] = {}
        self._worker_fn = worker_fn

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def submit(self, params: dict) -> str:
        """Enqueue a job.  Returns the new job_id."""
        job_id = f"job_{uuid.uuid4().hex[:10]}"
        record = JobRecord(job_id=job_id, params=params)
        self._jobs[job_id] = record
        self._queue.put_nowait(record)
        return job_id

    def get_status(self, job_id: str) -> dict | None:
        """Return the job record dict, or None if job_id is unknown."""
        record = self._jobs.get(job_id)
        return record.to_dict() if record else None

    # ------------------------------------------------------------------
    # Background worker – start once via asyncio.create_task()
    # ------------------------------------------------------------------

    async def run_worker(self) -> None:
        """
        Continuously drain the queue and execute the worker function.
        Start this coroutine as an asyncio background task during app lifespan.
        """
        while True:
            record = await self._queue.get()
            record.status = JobStatus.RUNNING
            try:
                record.result = await self._worker_fn(record.params)
                record.status = JobStatus.DONE
            except Exception as exc:  # noqa: BLE001
                record.error = str(exc)
                record.status = JobStatus.ERROR
            finally:
                self._queue.task_done()
