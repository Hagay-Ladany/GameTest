# Architecture – Godot ↔ Python AI Services Communication

## Protocol Decision: REST (HTTP/1.1 keep-alive) with optional WebSocket upgrade

### Why not pure WebSockets for everything?

| Criterion | REST (HTTP) | WebSocket |
|---|---|---|
| Request type | Stateless, one-shot generation | Stateful, streaming / real-time |
| Latency on localhost | < 5 ms round-trip | < 1 ms after handshake |
| Godot integration | `HttpRequest` node or `HttpClient` (C#) | `WebSocketClient` (more boilerplate) |
| Error handling | Standard HTTP status codes | Custom framing required |
| Best for | Sprite gen, story beats, single queries | Live narration stream, continuous updates |

### Recommended Approach (Phase 1 → MVP)

**Use REST** for all generation requests in Phase 1:

- `POST /text2sprite/generate` – one-shot sprite request; response is a cache URL.  
- `POST /story/generate` – one-shot narrative beat.  
- `GET /health` – liveness probe.

**Justification for local RTX 5070 Ti hardware:**

1. The service runs on `localhost`; round-trip overhead is negligible (< 2 ms).
2. HTTP keep-alive (default in `HttpClient`) amortises connection cost across requests.
3. Batched inference already handles GPU VRAM pressure; there is no need for a streaming transport at this stage.
4. REST endpoints are trivially testable with `curl` / Swagger UI (`/docs`).

**Upgrade path to WebSockets (Phase 3+):**

Add a FastAPI `WebSocket` route (`/story/stream`) for streaming LLM token output so  
the Godot HUD can display narrative text word-by-word in real time without polling.

---

## Service Topology

```
┌──────────────────────────────────┐       HTTP (localhost:8000)
│   Godot 4.x Engine (C#)          │ ─────────────────────────────► ┌───────────────────────────┐
│   engine/src/AIClient.cs          │                                 │  FastAPI  ai_services/    │
│                                  │ ◄───────────────────────────── │  main.py                  │
└──────────────────────────────────┘       JSON response             │                           │
                                                                     │  /text2sprite/generate    │
                                                                     │  /story/generate          │
                                                                     │  /health                  │
                                                                     └───────────┬───────────────┘
                                                                                 │
                                                              ┌──────────────────┴──────────────────┐
                                                              │                                     │
                                                   ┌──────────▼──────────┐             ┌────────────▼────────┐
                                                   │  text2sprite/        │             │  story_engine/       │
                                                   │  SDXL / ControlNet   │             │  LLaMA / Mistral     │
                                                   │  (ONNX / TensorRT)   │             │  (llama.cpp / vLLM)  │
                                                   └─────────────────────┘             └─────────────────────┘
                                                              │                                     │
                                                   ┌──────────▼─────────────────────────────────────▼──────┐
                                                   │          RTX 5070 Ti  –  batched VRAM tracks           │
                                                   │          ONNX Runtime / TensorRT acceleration          │
                                                   └────────────────────────────────────────────────────────┘
                                                              │
                                                   ┌──────────▼─────────────┐
                                                   │  data/media_cache/     │  ← NVMe SSD asset cache
                                                   │  data/models/          │  ← DVC-tracked checkpoints
                                                   └────────────────────────┘
```

---

## VRAM Strategy

- Each inference track (sprite gen, story gen) is allocated a dedicated CUDA stream.
- Requests are queued and executed in micro-batches to stay within VRAM budget.
- TensorRT / ONNX Runtime FP16 quantisation halves memory footprint vs FP32.
- `data/models/` is DVC-tracked; large checkpoints never touch Git history.

---

## Key File Locations (Phase 1)

| File | Purpose |
|---|---|
| `ai_services/main.py` | FastAPI app + router registration |
| `ai_services/api/text2sprite.py` | Sprite generation endpoint |
| `ai_services/api/story.py` | Story/narrative endpoint |
| `ai_services/utils/logger.py` | JSON metadata request logger |
| `ai_services/utils/hardware.py` | GPU detection + hardware profile |
| `engine/src/AIClient.cs` | Godot async C# HTTP client |
| `logs/ai_requests.jsonl` | Append-only metadata log (auto-created) |
