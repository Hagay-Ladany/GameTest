"""
Centralized JSON metadata logger for all AI generation requests.
Every request is logged for reproducibility and debugging.
"""
import json
import uuid
import logging
from datetime import datetime, timezone
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parents[2] / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

_metadata_log_path = LOG_DIR / "ai_requests.jsonl"

# Standard Python logger for service-level messages
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_DIR / "service.log"),
    ],
)
logger = logging.getLogger("ai_services")


def generate_request_id() -> str:
    """Return a short unique request identifier."""
    return f"req_{uuid.uuid4().hex[:8]}"


def log_request_metadata(
    player_input: str,
    world_state_id: str,
    model_params: dict,
    hardware_profile: dict,
    request_id: str | None = None,
) -> dict:
    """
    Build and persist a JSON metadata record for a single AI generation request.

    Returns the metadata dict so callers can embed it in API responses.
    """
    if request_id is None:
        request_id = generate_request_id()

    metadata = {
        "request_id": request_id,
        "player_input": player_input,
        "world_state_id": world_state_id,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "model_params": model_params,
        "hardware_profile": hardware_profile,
    }

    with _metadata_log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(metadata) + "\n")

    logger.info("Request logged: %s", request_id)
    return metadata
