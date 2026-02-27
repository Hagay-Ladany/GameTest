"""
story_engine/llm.py – Structured Narrative Generation
======================================================

Uses llama-cpp-python with a GBNF (GGML BNF) grammar to guarantee the model
always produces a valid JSON object containing the keys ``narrative`` and
``choices``.

Key design decisions
--------------------
* **Global loading**: the ``Llm`` singleton is constructed once at app startup
  (via the FastAPI lifespan hook) to avoid cold-start penalties on every request.
* **Hardware acceleration**: ``n_gpu_layers=-1`` offloads all layers to the
  GPU; fall back to CPU-only when CUDA is unavailable.
* **Grammar enforcement**: GBNF intercepts the sampler at the token level so
  the LLM can never emit a malformed JSON response.

The module degrades gracefully when ``llama-cpp-python`` is not installed
(returns a stub response), so the FastAPI service still starts in environments
without GPU/model files.
"""
from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger("ai_services.story_engine")

# ---------------------------------------------------------------------------
# GBNF grammar – forces output to be a JSON object with required keys
# ---------------------------------------------------------------------------

_NARRATIVE_GRAMMAR = r"""
root   ::= object
object ::= "{" ws "\"narrative\"" ws ":" ws string "," ws "\"choices\"" ws ":" ws choices-array ws "}"
choices-array ::= "[" ws choice ("," ws choice)* ws "]"
choice ::= "{" ws "\"id\"" ws ":" ws number "," ws "\"text\"" ws ":" ws string ws "}"
string ::= "\"" ([^"\\] | "\\" .)* "\""
number ::= [0-9]+
ws     ::= [ \t\n]*
"""

# ---------------------------------------------------------------------------
# Singleton wrapper
# ---------------------------------------------------------------------------

_llm = None  # module-level singleton; set by load()


def load(
    model_path: str | None = None,
    n_gpu_layers: int = -1,
    n_ctx: int = 2048,
) -> None:
    """
    Load (or reload) the LLM from *model_path*.

    Parameters
    ----------
    model_path:
        Path to the GGUF model file.  Falls back to the ``LLM_MODEL_PATH``
        environment variable, then to a default path relative to the repo.
    n_gpu_layers:
        Number of transformer layers to offload to GPU.  ``-1`` means all.
    n_ctx:
        Context window size in tokens.
    """
    global _llm  # noqa: PLW0603

    if model_path is None:
        model_path = os.environ.get(
            "LLM_MODEL_PATH",
            os.path.join(
                os.path.dirname(__file__),
                "..",
                "..",
                "data",
                "models",
                "mistral-7b-instruct-v0.2.Q4_K_M.gguf",
            ),
        )

    try:
        from llama_cpp import Llama  # type: ignore[import]

        logger.info("Loading LLM from %s (n_gpu_layers=%d) …", model_path, n_gpu_layers)
        _llm = Llama(
            model_path=model_path,
            n_gpu_layers=n_gpu_layers,
            n_ctx=n_ctx,
            verbose=False,
        )
        logger.info("LLM loaded successfully.")
    except ImportError:
        logger.warning(
            "llama-cpp-python not installed – LLM inference will return stub responses."
        )
        _llm = None
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to load LLM: %s – using stub responses.", exc)
        _llm = None


def generate(
    player_input: str,
    world_state_id: str = "00000",
    temperature: float = 0.72,
    max_tokens: int = 256,
) -> dict:
    """
    Generate a structured narrative response.

    Returns a dict with keys ``narrative`` (str) and ``choices`` (list of
    ``{"id": int, "text": str}`` dicts).  Falls back to a deterministic stub
    when the model is unavailable.
    """
    if _llm is None:
        return _stub_response(player_input)

    try:
        from llama_cpp import LlamaGrammar  # type: ignore[import]

        grammar = LlamaGrammar.from_string(_NARRATIVE_GRAMMAR)

        prompt = (
            f"[INST] You are an AI game master for a 2D adventure game.\n"
            f"World state: {world_state_id}\n"
            f"Player action: {player_input}\n"
            "Respond with a JSON object containing 'narrative' (a short scene description) "
            "and 'choices' (a list of 2-4 player options with 'id' and 'text'). [/INST]"
        )

        output = _llm(
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            grammar=grammar,
            stop=["[INST]"],
        )

        raw_json = output["choices"][0]["text"].strip()
        return json.loads(raw_json)

    except Exception as exc:  # noqa: BLE001
        logger.error("LLM inference error: %s", exc)
        return _stub_response(player_input)


# ---------------------------------------------------------------------------
# Stub fallback
# ---------------------------------------------------------------------------

def _stub_response(player_input: str) -> dict:
    return {
        "narrative": (
            f"[STUB] You chose to '{player_input}'. "
            "The world shifts around you… (narrative engine not yet active)"
        ),
        "choices": [
            {"id": 1, "text": "Move north"},
            {"id": 2, "text": "Move south"},
            {"id": 3, "text": "Examine surroundings"},
        ],
    }
