"""
FastAPI router – /text2sprite

Accepts a text description (and an optional base64-encoded ControlNet sketch)
and enqueues an SDXL + ControlNet (Canny) sprite generation job.

VRAM strategy: requests are queued via an asyncio.Queue worker to avoid VRAM
overflow.  The client submits a job and receives a ``job_id``, then polls
``GET /text2sprite/status/{job_id}`` until the job is ``"done"`` or ``"error"``.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ai_services.job_queue import InferenceQueue
from ai_services.text2sprite import sdxl
from ai_services.utils.hardware import get_hardware_profile
from ai_services.utils.logger import generate_request_id, log_request_metadata

router = APIRouter()

# ---------------------------------------------------------------------------
# Async worker function
# ---------------------------------------------------------------------------

async def _sdxl_worker(params: dict) -> dict:
    """Run SDXL + ControlNet inference for a queued sprite job."""
    sprite_path = sdxl.generate(
        prompt=params["player_input"],
        sketch_b64=params.get("sketch_b64"),
        width=params.get("width", 64),
        height=params.get("height", 64),
        filename=params.get("request_id"),
    )
    return {"sprite_path": sprite_path}


# Module-level queue – background worker is started via the app lifespan.
sprite_queue = InferenceQueue(worker_fn=_sdxl_worker)

# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class SpriteRequest(BaseModel):
    player_input: str = Field(..., examples=["a knight in golden armour"])
    world_state_id: str = Field(default="00000", examples=["00023"])
    width: int = Field(default=64, ge=16, le=512)
    height: int = Field(default=64, ge=16, le=512)
    temperature: float = Field(default=0.72, ge=0.0, le=1.0)
    batch_mode: bool = True
    sketch_b64: str | None = Field(
        default=None,
        description=(
            "Optional base64-encoded PNG sketch from the Godot client.  "
            "The backend runs Canny edge detection on this image and uses the "
            "result as the ControlNet conditioning so the generated sprite "
            "matches the intended collision boundaries."
        ),
    )


class SpriteSubmitResponse(BaseModel):
    job_id: str
    status: str
    request_id: str
    metadata: dict


class SpriteStatusResponse(BaseModel):
    job_id: str
    status: str
    sprite_path: str | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/generate",
    response_model=SpriteSubmitResponse,
    summary="Submit a sprite generation job",
)
async def generate_sprite(req: SpriteRequest) -> SpriteSubmitResponse:
    """
    Accepts a natural-language description (and an optional ControlNet sketch)
    and enqueues an SDXL sprite generation job.

    Returns a ``job_id`` immediately.  Poll ``GET /text2sprite/status/{job_id}``
    until ``status`` is ``"done"`` or ``"error"``.
    """
    request_id = generate_request_id()
    hw = get_hardware_profile(batch_mode=req.batch_mode)

    metadata = log_request_metadata(
        player_input=req.player_input,
        world_state_id=req.world_state_id,
        model_params={"temperature": req.temperature, "width": req.width, "height": req.height},
        hardware_profile=hw,
        request_id=request_id,
    )

    job_id = sprite_queue.submit(
        params={
            "player_input": req.player_input,
            "world_state_id": req.world_state_id,
            "width": req.width,
            "height": req.height,
            "sketch_b64": req.sketch_b64,
            "request_id": request_id,
        }
    )

    return SpriteSubmitResponse(
        job_id=job_id,
        status="queued",
        request_id=request_id,
        metadata=metadata,
    )


@router.get(
    "/status/{job_id}",
    response_model=SpriteStatusResponse,
    summary="Poll the status of a sprite generation job",
)
async def sprite_job_status(job_id: str) -> SpriteStatusResponse:
    """
    Returns the current status of a previously submitted sprite job.

    * ``status: "queued"``  – job is waiting in the queue.
    * ``status: "running"`` – SDXL inference is in progress.
    * ``status: "done"``    – ``sprite_path`` contains the saved PNG file path.
    * ``status: "error"``   – ``error`` field contains the failure reason.
    """
    record = sprite_queue.get_status(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

    result = record.get("result") or {}
    return SpriteStatusResponse(
        job_id=job_id,
        status=record["status"],
        sprite_path=result.get("sprite_path") if result else None,
        error=record.get("error"),
    )
