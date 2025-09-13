from dotenv import load_dotenv
import os


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

