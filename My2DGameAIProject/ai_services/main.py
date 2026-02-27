"""
My2DGameAI Services – FastAPI entry point
=========================================

Starts two modular routers:
  • /text2sprite  – text-to-sprite generation pipeline
  • /story        – narrative / story-engine LLM pipeline

Run locally:
    uvicorn ai_services.main:app --host 0.0.0.0 --port 8000 --reload
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ai_services.api import story, text2sprite

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
