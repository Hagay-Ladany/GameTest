"""
FastAPI router – /story

Accepts a player action and world state, then returns a generated narrative
response (dialogue, scene description, next-beat hint).

VRAM strategy: LLM inference is queued and run in batches.  In Phase 2 this
will call a quantised Mistral / LLaMA model via llama.cpp or vLLM.
"""
from fastapi import APIRouter
from pydantic import BaseModel, Field

from ai_services.utils.hardware import get_hardware_profile
from ai_services.utils.logger import generate_request_id, log_request_metadata

router = APIRouter()

# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class StoryRequest(BaseModel):
    player_input: str = Field(..., examples=["move north"])
    world_state_id: str = Field(default="00000", examples=["00023"])
    temperature: float = Field(default=0.72, ge=0.0, le=2.0)
    max_len: int = Field(default=256, ge=16, le=2048)
    batch_mode: bool = True


class StoryResponse(BaseModel):
    request_id: str
    status: str
    narrative: str | None = None
    metadata: dict


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post("/generate", response_model=StoryResponse, summary="Generate a narrative response")
async def generate_story(req: StoryRequest) -> StoryResponse:
    """
    Accepts a player action + world state and returns the next story beat.

    **Phase 1 stub**: echoes input and returns a placeholder narrative.  In
    later phases this will call a quantised LLM with RAG-backed world state.
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

    # TODO (Phase 2): call the LLM inference pipeline.
    narrative = (
        f"[STUB] You chose to '{req.player_input}'. "
        "The world shifts around you… (narrative engine coming in Phase 2)"
    )

    return StoryResponse(
        request_id=request_id,
        status="ok",
        narrative=narrative,
        metadata=metadata,
    )
