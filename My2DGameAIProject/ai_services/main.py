"""
My2DGameAI Services – FastAPI entry point
=========================================

Starts two modular routers:
  • /text2sprite  – text-to-sprite generation pipeline (SDXL + ControlNet)
  • /story        – narrative / story-engine LLM pipeline (llama-cpp-python)

Models are loaded once during the app lifespan (startup) to avoid cold-start
penalties.  Async queue workers are also started here.

Run locally:
    uvicorn ai_services.main:app --host 0.0.0.0 --port 8000 --reload
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ai_services.api import story, text2sprite
from ai_services.story_engine import llm as story_llm
from ai_services.text2sprite import sdxl


# ---------------------------------------------------------------------------
# Lifespan – load models once at startup, start queue workers
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan context manager.

    Startup:
      • Load the LLM (llama-cpp-python) with GPU layer offloading.
      • Load the SDXL + ControlNet pipeline with float16 + cpu_offload.
      • Start asyncio background workers that drain the inference queues.

    Shutdown:
      • Worker tasks are cancelled gracefully.
    """
    # Load AI models (gracefully no-ops when model files / libraries are absent)
    story_llm.load()
    sdxl.load()

    # Start background queue workers
    story_worker_task = asyncio.create_task(
        story.story_queue.run_worker(), name="story_queue_worker"
    )
    sprite_worker_task = asyncio.create_task(
        text2sprite.sprite_queue.run_worker(), name="sprite_queue_worker"
    )

    yield  # application runs here

    # Graceful shutdown
    story_worker_task.cancel()
    sprite_worker_task.cancel()


# ---------------------------------------------------------------------------
# App instance
# ---------------------------------------------------------------------------

app = FastAPI(
    title="My2DGameAI Services",
    description=(
        "FastAPI microservices powering AI-driven sprite generation and "
        "narrative logic for the My2DGameAIProject Godot client."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# Allow the local Godot client (and the Godot editor's HTTP export) to reach
# this service without CORS errors during development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten in production
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Mount routers
# ---------------------------------------------------------------------------

app.include_router(text2sprite.router, prefix="/text2sprite", tags=["text2sprite"])
app.include_router(story.router, prefix="/story", tags=["story"])


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health", tags=["meta"])
async def health() -> dict:
    """Returns service liveness status."""
    return {"status": "ok", "service": "My2DGameAI Services", "version": app.version}
