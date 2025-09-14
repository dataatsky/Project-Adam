from dotenv import load_dotenv
import os
import json


# Load environment from .env if present
load_dotenv(".env")

# LLM / Psyche service
PSYCHE_LLM_API_URL = os.getenv("PSYCHE_LLM_API_URL", "http://127.0.0.1:5000/")

# Pinecone / embeddings
PINECONE_API_KEY = os.getenv("PINECONE")
PINECONE_ENVIRONMENT = os.getenv("PINECONE_ENVIRONMENT")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME")
SENTENCE_MODEL = os.getenv("SENTENCE_MODEL")

# Logging
LOG_FILE = os.getenv("LOG_FILE", "adam_loop.log")

# Loop pacing
CYCLE_SLEEP = float(os.getenv("CYCLE_SLEEP", "5"))
IMAGINE_TOP_K = int(os.getenv("IMAGINE_TOP_K", "3"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# Psyche client
PSYCHE_TIMEOUT = float(os.getenv("PSYCHE_TIMEOUT", "30"))
PSYCHE_RETRIES = int(os.getenv("PSYCHE_RETRIES", "2"))
PSYCHE_BACKOFF = float(os.getenv("PSYCHE_BACKOFF", "0.5"))

# Memory batching
MEMORY_UPSERT_BATCH = int(os.getenv("MEMORY_UPSERT_BATCH", "5"))

# Agent initial status
def _get_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except Exception:
        return default

# Allow full JSON override via AGENT_STATUS_JSON
_AGENT_STATUS_JSON = os.getenv("AGENT_STATUS_JSON")
if _AGENT_STATUS_JSON:
    try:
        AGENT_STATUS = json.loads(_AGENT_STATUS_JSON)
    except Exception as e:
        print(f"⚠️ AGENT_STATUS_JSON parse failed: {e}. Falling back to individual env values.")
        AGENT_STATUS = None
else:
    AGENT_STATUS = None

if not AGENT_STATUS:
    AGENT_STATUS = {
        "emotional_state": {
            "mood": os.getenv("AGENT_MOOD", "neutral"),
            "level": _get_float("AGENT_LEVEL", 0.1),
        },
        "personality": {
            "curiosity": _get_float("AGENT_CURIOSITY", 0.8),
            "bravery": _get_float("AGENT_BRAVERY", 0.6),
            "caution": _get_float("AGENT_CAUTION", 0.7),
        },
        "needs": {
            "hunger": _get_float("AGENT_HUNGER", 0.1),
        },
        "goal": os.getenv("AGENT_GOAL", "Find the source of the strange noises in the house."),
    }
