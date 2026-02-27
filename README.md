# My2DGameAIProject

A 2D game project built with **Godot 4.x (C#)** that integrates AI-powered sprite generation and dynamic narrative storytelling via Python microservices.

## Overview

My2DGameAIProject bridges a Godot game engine frontend with Python AI backends running on local GPU hardware. The game can generate procedural 2D sprites from text descriptions and produce dynamic story narratives in response to player actions — all powered by diffusion models and large language models running locally.

## Project Structure

```
My2DGameAIProject/
├── ai_services/            # Python FastAPI microservices
│   ├── main.py             # FastAPI app entry point
│   ├── requirements.txt    # Python dependencies
│   ├── api/
│   │   ├── text2sprite.py  # Sprite generation endpoint
│   │   └── story.py        # Narrative generation endpoint
│   ├── utils/
│   │   ├── hardware.py     # GPU detection & profiling
│   │   └── logger.py       # JSON metadata logging
│   ├── text2sprite/        # SDXL / ControlNet inference (Phase 2)
│   └── story_engine/       # LLaMA / Mistral inference (Phase 2)
├── engine/
│   ├── src/
│   │   └── AIClient.cs     # Godot C# async HTTP client singleton
│   ├── configs/            # Engine configuration files
│   └── scenes/             # Godot scene definitions
├── data/
│   ├── media_cache/        # Generated sprite asset cache
│   └── models/             # DVC-tracked model checkpoints
├── assets/                 # Static game art & assets
├── logs/                   # JSONL request metadata logs
└── docs/
    └── architecture.md     # Detailed system design documentation
```

## Technologies

| Layer | Technology |
|---|---|
| Game Engine | Godot 4.x (C#) |
| AI Services | Python 3, FastAPI, Uvicorn |
| Sprite Generation | SDXL / ControlNet (ONNX Runtime / TensorRT) |
| Narrative Engine | LLaMA / Mistral (llama.cpp / vLLM) |
| GPU | NVIDIA RTX 5070 Ti (CUDA) |
| Model Versioning | DVC |

## Getting Started

### Prerequisites

- [Godot 4.x](https://godotengine.org/) with .NET / C# support
- Python 3.10+
- NVIDIA GPU with CUDA support (RTX recommended)

### Running the AI Services

```bash
# Install Python dependencies
cd My2DGameAIProject/ai_services
pip install -r requirements.txt

# Start the FastAPI server
uvicorn ai_services.main:app --host 0.0.0.0 --port 8000 --reload
```

The API will be available at `http://localhost:8000`. Interactive docs (Swagger UI) are at `http://localhost:8000/docs`.

### Running the Game

Open `My2DGameAIProject/` in the Godot editor and run the project. The `AIClient` singleton connects to the Python services at `http://127.0.0.1:8000` by default.

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/text2sprite/generate` | Generate a sprite from a text description |
| `POST` | `/story/generate` | Generate a narrative beat from player input |
| `GET` | `/health` | Service liveness check |

### Example Request (Sprite)

```bash
curl -X POST http://localhost:8000/text2sprite/generate \
  -H "Content-Type: application/json" \
  -d '{"player_input": "a knight in golden armour", "world_state_id": "00023", "width": 64, "height": 64}'
```

### Example Request (Story)

```bash
curl -X POST http://localhost:8000/story/generate \
  -H "Content-Type: application/json" \
  -d '{"player_input": "the player enters the dark forest", "world_state_id": "00023"}'
```

## Architecture

The Godot client communicates with the FastAPI backend over HTTP on localhost. Each generation request is queued and processed in micro-batches on the GPU.

```
Godot 4.x (AIClient.cs)
        │  HTTP POST (localhost:8000)
        ▼
FastAPI (ai_services/main.py)
        ├── /text2sprite  →  SDXL / ControlNet  ─┐
        └── /story        →  LLaMA / Mistral     ─┤
                                                   ▼
                                         RTX 5070 Ti GPU
                                         (ONNX / TensorRT)
                                                   │
                                         data/media_cache/
                                         data/models/
```

For full details, see [`docs/architecture.md`](My2DGameAIProject/docs/architecture.md).

## Roadmap

- **Phase 1 (current)** – Framework scaffolding; API endpoints return placeholder responses.
- **Phase 2** – Implement SDXL sprite generation and LLM narrative inference pipelines.
- **Phase 3** – WebSocket streaming for real-time word-by-word narrative display in the Godot HUD.
