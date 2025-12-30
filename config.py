from dotenv import load_dotenv
import os
import json


# Load environment from .env if present
load_dotenv(".env")

# LLM / Psyche service
PSYCHE_LLM_API_URL = os.getenv("PSYCHE_LLM_API_URL", "http://127.0.0.1:5001/")

# Pinecone / embeddings
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY") or os.getenv("PINECONE")
PINECONE_ENVIRONMENT = os.getenv("PINECONE_ENVIRONMENT")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME")
PINECONE_CLOUD = os.getenv("PINECONE_CLOUD")
PINECONE_REGION = os.getenv("PINECONE_REGION")
SENTENCE_MODEL = os.getenv("SENTENCE_MODEL")

# Local vector store (Chroma)
MEMORY_BACKEND = (os.getenv("MEMORY_BACKEND", "chroma") or "chroma").strip().lower()
CHROMA_PATH = os.getenv("CHROMA_PATH", "./chroma")
CHROMA_COLLECTION = os.getenv("CHROMA_COLLECTION", PINECONE_INDEX_NAME or "adam-memory")


def _infer_cloud_region(env: str | None) -> tuple[str | None, str | None]:
    """Best-effort compatibility bridge from legacy environment strings."""
    if not env:
        return (None, None)
    parts = env.split("-")
    if len(parts) >= 3:
        # e.g. us-west1-gcp → (gcp, us-west1)
        region = "-".join(parts[:-1])
        cloud = parts[-1]
        return (cloud, region)
    if len(parts) == 2:
        # e.g. us-east-1 → assume aws
        return (parts[0], parts[1])
    return (None, env)


if not PINECONE_CLOUD or not PINECONE_REGION:
    inferred_cloud, inferred_region = _infer_cloud_region(PINECONE_ENVIRONMENT)
    PINECONE_CLOUD = PINECONE_CLOUD or inferred_cloud
    PINECONE_REGION = PINECONE_REGION or inferred_region

# Logging
LOG_FILE = os.getenv("LOG_FILE", "adam_behavior_log.csv")

# Loop pacing
CYCLE_SLEEP = float(os.getenv("CYCLE_SLEEP", "5"))
IMAGINE_TOP_K = int(os.getenv("IMAGINE_TOP_K", "3"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# Security harness
ADAMSEC_ENABLED = os.getenv("ADAMSEC_ENABLED", "0") not in {"0", "false", "False", ""}
ADAMSEC_PLAYBOOK = os.getenv("ADAMSEC_PLAYBOOK")
ADAMSEC_LOG = os.getenv("ADAMSEC_LOG", "security_events.log")

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
