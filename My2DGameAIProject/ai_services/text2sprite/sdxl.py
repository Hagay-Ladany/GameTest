"""
text2sprite/sdxl.py – Context-Aware Image Synthesis
====================================================

Uses Stable Diffusion XL (SDXL) with a ControlNet (Canny) conditioning stage
so that the generated sprite matches the collision geometry supplied by the
Godot client as a base64-encoded sketch image.

Key design decisions
--------------------
* **ControlNet (Canny)**: the client submits a geometric sketch; the backend
  extracts Canny edges so the generated image respects the intended collision
  boundaries.
* **Memory optimisation**: the pipeline runs in ``torch.float16`` and calls
  ``enable_model_cpu_offload()`` to prevent VRAM exhaustion on consumer GPUs.
* **Global loading**: models are loaded once at startup (via the FastAPI
  lifespan hook) and reused across requests.

The module degrades gracefully when ``diffusers`` / ``torch`` are not
installed, returning a stub PNG path so the rest of the stack stays functional
in CI environments.
"""
from __future__ import annotations

import base64
import io
import logging
import os
from pathlib import Path

logger = logging.getLogger("ai_services.text2sprite")

# ---------------------------------------------------------------------------
# Singleton pipeline – set by load()
# ---------------------------------------------------------------------------

_pipe = None  # ControlNetPipeline or None


def load(
    sdxl_model_id: str = "stabilityai/stable-diffusion-xl-base-1.0",
    controlnet_model_id: str = "diffusers/controlnet-canny-sdxl-1.0",
) -> None:
    """
    Load the SDXL + ControlNet pipeline once at startup.

    Uses ``torch.float16`` and ``enable_model_cpu_offload()`` to minimise VRAM
    usage while still leveraging GPU acceleration where available.
    """
    global _pipe  # noqa: PLW0603

    try:
        import torch  # type: ignore[import]
        from diffusers import ControlNetModel, StableDiffusionXLControlNetPipeline  # type: ignore[import]

        logger.info("Loading ControlNet model: %s …", controlnet_model_id)
        controlnet = ControlNetModel.from_pretrained(
            controlnet_model_id,
            torch_dtype=torch.float16,
        )

        logger.info("Loading SDXL pipeline: %s …", sdxl_model_id)
        _pipe = StableDiffusionXLControlNetPipeline.from_pretrained(
            sdxl_model_id,
            controlnet=controlnet,
            torch_dtype=torch.float16,
        )

        # Offload model blocks to CPU between inference steps to reduce peak VRAM.
        _pipe.enable_model_cpu_offload()
        logger.info("SDXL + ControlNet pipeline loaded and optimised.")

    except ImportError:
        logger.warning(
            "diffusers / torch not installed – sprite generation will return stub paths."
        )
        _pipe = None
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to load SDXL pipeline: %s – using stub responses.", exc)
        _pipe = None


def generate(
    prompt: str,
    sketch_b64: str | None = None,
    width: int = 64,
    height: int = 64,
    num_inference_steps: int = 30,
    controlnet_conditioning_scale: float = 0.5,
    output_dir: str | None = None,
    filename: str | None = None,
) -> str:
    """
    Generate a sprite PNG using SDXL + ControlNet (Canny conditioning).

    Parameters
    ----------
    prompt:
        Text description of the sprite to generate.
    sketch_b64:
        Optional base64-encoded PNG sketch from the Godot client.  When
        provided, Canny edge detection is applied and used as the ControlNet
        conditioning image so the output matches the intended collision
        boundaries.
    width / height:
        Output image dimensions in pixels.
    output_dir:
        Directory to save the generated PNG.  Defaults to
        ``data/media_cache/`` relative to the repository root.
    filename:
        Output filename (without extension).  A UUID is used if omitted.

    Returns
    -------
    str
        Absolute file path to the saved PNG.
    """
    import uuid as _uuid

    if output_dir is None:
        output_dir = os.path.join(
            os.path.dirname(__file__), "..", "..", "data", "media_cache"
        )
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    if filename is None:
        filename = _uuid.uuid4().hex

    out_path = str(Path(output_dir) / f"{filename}.png")

    if _pipe is None:
        # Return a stub path when the pipeline is unavailable.
        logger.debug("SDXL pipeline unavailable; returning stub path: %s", out_path)
        return out_path

    try:
        import numpy as np  # type: ignore[import]
        from PIL import Image  # type: ignore[import]

        # ------------------------------------------------------------------
        # Prepare ControlNet conditioning image from client sketch
        # ------------------------------------------------------------------
        if sketch_b64:
            sketch_bytes = base64.b64decode(sketch_b64)
            sketch_img = Image.open(io.BytesIO(sketch_bytes)).convert("RGB")
            canny_img = _apply_canny(sketch_img)
        else:
            # Fall back to a blank (black) conditioning image.
            canny_img = Image.fromarray(
                np.zeros((height, width, 3), dtype=np.uint8)
            )

        # Resize conditioning image to match requested output dimensions.
        canny_img = canny_img.resize((width, height))

        # ------------------------------------------------------------------
        # Run inference
        # ------------------------------------------------------------------
        result = _pipe(
            prompt=prompt,
            image=canny_img,
            width=width,
            height=height,
            num_inference_steps=num_inference_steps,
            controlnet_conditioning_scale=controlnet_conditioning_scale,
        )

        image: "Image.Image" = result.images[0]
        image.save(out_path)
        logger.info("Sprite saved to %s", out_path)
        return out_path

    except Exception as exc:  # noqa: BLE001
        logger.error("SDXL inference error: %s", exc)
        return out_path


# ---------------------------------------------------------------------------
# Canny edge detection helper
# ---------------------------------------------------------------------------

def _apply_canny(image: "Image.Image") -> "Image.Image":
    """
    Apply Canny edge detection to *image* and return the result as a PIL Image.

    Uses OpenCV when available; falls back to a simple Pillow edge filter.
    """
    try:
        import cv2  # type: ignore[import]
        import numpy as np  # type: ignore[import]

        img_array = np.array(image)
        gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
        edges = cv2.Canny(gray, threshold1=100, threshold2=200)
        # Convert single-channel edges back to 3-channel RGB for ControlNet.
        edges_rgb = cv2.cvtColor(edges, cv2.COLOR_GRAY2RGB)
        from PIL import Image  # type: ignore[import]
        return Image.fromarray(edges_rgb)
    except ImportError:
        # Pillow-only fallback: use the FIND_EDGES filter.
        from PIL import ImageFilter  # type: ignore[import]
        return image.convert("L").filter(ImageFilter.FIND_EDGES).convert("RGB")
