"""
FastAPI router – /story

Accepts a player action and world state, then returns a generated narrative
response (dialogue, scene description, next-beat hint).

VRAM strategy: LLM inference is queued via an asyncio.Queue worker.  The
client submits a job and receives a job_id, then polls GET /story/status/{job_id}
until the job is "done" or "error".
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ai_services.job_queue import InferenceQueue
from ai_services.story_engine import llm as story_llm
from ai_services.utils.hardware import get_hardware_profile
from ai_services.utils.logger import generate_request_id, log_request_metadata

router = APIRouter()

# ---------------------------------------------------------------------------
# Async worker function
# ---------------------------------------------------------------------------

async def _llm_worker(params: dict) -> dict:
    """Run LLM inference for a queued story job."""
    return story_llm.generate(
        player_input=params["player_input"],
        world_state_id=params.get("world_state_id", "00000"),
        temperature=params.get("temperature", 0.72),
        max_tokens=params.get("max_len", 256),
    )


# Module-level queue – background worker is started via the app lifespan.
story_queue = InferenceQueue(worker_fn=_llm_worker)

# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class StoryRequest(BaseModel):
    player_input: str = Field(..., examples=["move north"])
    world_state_id: str = Field(default="00000", examples=["00023"])
    temperature: float = Field(default=0.72, ge=0.0, le=2.0)
    max_len: int = Field(default=256, ge=16, le=2048)
    batch_mode: bool = True


class StorySubmitResponse(BaseModel):
    job_id: str
    status: str
    request_id: str
    metadata: dict


class StoryStatusResponse(BaseModel):
    job_id: str
    status: str
    narrative: str | None = None
    choices: list | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/generate",
    response_model=StorySubmitResponse,
    summary="Submit a narrative generation job",
)
async def generate_story(req: StoryRequest) -> StorySubmitResponse:
    """
    Accepts a player action + world state and enqueues an LLM inference job.

    Returns a ``job_id`` immediately.  Poll ``GET /story/status/{job_id}``
    until ``status`` is ``"done"`` or ``"error"``.
    """
    request_id = generate_request_id()
    hw = get_hardware_profile(batch_mode=req.batch_mode)

    metadata = log_request_metadata(
        player_input=req.player_input,
        world_state_id=req.world_state_id,
        model_params={"temperature": req.temperature, "max_len": req.max_len},
        hardware_profile=hw,
        request_id=request_id,
    )

    job_id = story_queue.submit(
        params={
            "player_input": req.player_input,
            "world_state_id": req.world_state_id,
            "temperature": req.temperature,
            "max_len": req.max_len,
        }
    )

    return StorySubmitResponse(
        job_id=job_id,
        status="queued",
        request_id=request_id,
        metadata=metadata,
    )


@router.get(
    "/status/{job_id}",
    response_model=StoryStatusResponse,
    summary="Poll the status of a narrative generation job",
)
async def story_job_status(job_id: str) -> StoryStatusResponse:
    """
    Returns the current status of a previously submitted story job.

    * ``status: "queued"``  – job is waiting in the queue.
    * ``status: "running"`` – LLM inference is in progress.
    * ``status: "done"``    – ``narrative`` and ``choices`` are populated.
    * ``status: "error"``   – ``error`` field contains the failure reason.
    """
    record = story_queue.get_status(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

    result = record.get("result") or {}
    return StoryStatusResponse(
        job_id=job_id,
        status=record["status"],
        narrative=result.get("narrative") if result else None,
        choices=result.get("choices") if result else None,
        error=record.get("error"),
    )
