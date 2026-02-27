"""
FastAPI router – /text2sprite

Accepts a text description and returns a URL / path to the generated sprite
(or a base64-encoded PNG in the stub phase).  Heavy inference is intentionally
deferred so this file only wires up the API contract.

VRAM strategy: requests are queued and processed in batches to avoid overflow
on the RTX 5070 Ti.  A real implementation would call a batched diffusion
pipeline here (e.g. SDXL-Turbo via TensorRT/ONNX Runtime).
"""
from fastapi import APIRouter
from pydantic import BaseModel, Field

from ai_services.utils.hardware import get_hardware_profile
from ai_services.utils.logger import generate_request_id, log_request_metadata

router = APIRouter()

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


class SpriteResponse(BaseModel):
    request_id: str
    status: str
    sprite_url: str | None = None
    metadata: dict


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post("/generate", response_model=SpriteResponse, summary="Generate a 2-D sprite from text")
async def generate_sprite(req: SpriteRequest) -> SpriteResponse:
    """
    Accepts a natural-language description and schedules sprite generation.

    **Phase 1 stub**: returns a placeholder URL.  In later phases this will
    invoke a batched SDXL / ControlNet pipeline via ONNX Runtime.
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

    # TODO (Phase 2): dispatch to the batched diffusion pipeline.
    sprite_url = f"/data/media_cache/{request_id}.png"

    return SpriteResponse(
        request_id=request_id,
        status="queued",
        sprite_url=sprite_url,
        metadata=metadata,
    )
