import time
from typing import List, Tuple, Optional

from sentence_transformers import SentenceTransformer
from pinecone import Pinecone
try:
    from pinecone import ServerlessSpec
except Exception:  # pragma: no cover - optional dependency in older SDKs
    ServerlessSpec = None
import logging


def _parse_environment(env: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    if not env:
        return (None, None)
    parts = (env or "").split("-")
    if len(parts) >= 3:
        region = "-".join(parts[:-1])
        cloud = parts[-1]
        return (cloud, region)
    if len(parts) == 2:
        return (parts[0], parts[1])
    return (None, env)


FOUNDATIONAL_MEMORIES = [
    "As a child, the sound of a phone ringing often meant bad news, making me feel anxious.",
    "I remember my mother humming a gentle tune while she worked in the kitchen. It always made me feel calm.",
    "A sudden knock on the door once led to an unpleasant surprise. I've been wary of unexpected visitors ever since.",
    "I enjoy the quiet solitude of reading. Books are a safe escape from a noisy world.",
    "Loud, chaotic noises like static on a TV have always been unsettling to me.",
    "I find the gentle sound of rain on a windowpane to be very soothing.",
    "I have a recurring dream about a locked door that I can't open, which fills me with a sense of unease and curiosity.",
]


class MemoryStore:
    """Wrapper around SentenceTransformer + Pinecone index.

    On failures, methods degrade gracefully to no-ops.
    """

    def __init__(
        self,
        *,
        api_key: Optional[str],
        environment: Optional[str],
        index_name: Optional[str],
        model_name: Optional[str],
        cloud: Optional[str] = None,
        region: Optional[str] = None,
        dimension: Optional[int] = None,
        batch_size: int = 5,
    ):
        self.log = logging.getLogger(__name__ + ".MemoryStore")
        self.model = None
        self.pc = None
        self.index = None
        self.dimension = dimension
        self._batch_size = int(batch_size)
        self._buffer: List[str] = []
        # Defer heavy init until first use
        self._api_key = api_key
        self._env = environment
        self._index_name = index_name
        self._model_name = model_name
        self._cloud = (cloud or "").strip() or None
        self._region = (region or "").strip() or None
        if (not self._cloud or not self._region) and self._env:
            inferred = _parse_environment(self._env)
            self._cloud = self._cloud or inferred[0]
            self._region = self._region or inferred[1]

    def _ensure_ready(self):
        # Initialize model lazily
        if self.model is None:
            try:
                if self._model_name:
                    self.model = SentenceTransformer(self._model_name)
                    self.log.info("SentenceTransformer model loaded")
                    try:
                        dim = int(self.model.get_sentence_embedding_dimension())
                        self.dimension = dim
                    except Exception:
                        pass
            except Exception as e:
                self.log.warning(f"SentenceTransformer init failed: {e}")
                self.model = None
        if self.dimension is None:
            # fall back to ST default miniLM size
            self.dimension = 384
        # Initialize Pinecone lazily
        if self.index is None and self._api_key and self._index_name:
            try:
                self.pc = self.pc or Pinecone(api_key=self._api_key)
                indexes = self.pc.list_indexes()
                if hasattr(indexes, "names"):
                    names = set(indexes.names())
                elif isinstance(indexes, (list, tuple, set)):
                    names = set(indexes)
                else:
                    names = set(indexes or [])
                if self._index_name not in names:
                    if not ServerlessSpec:
                        self.log.warning("Pinecone SDK missing ServerlessSpec; cannot auto-create index.")
                        return
                    cloud = self._cloud or "aws"
                    region = self._region or "us-east-1"
                    if not self._cloud or not self._region:
                        self.log.info(f"Using default Pinecone location cloud={cloud} region={region}")
                    self.log.info(f"Creating Pinecone index: {self._index_name}")
                    spec = ServerlessSpec(cloud=cloud, region=region)
                    self.pc.create_index(
                        name=self._index_name,
                        dimension=int(self.dimension),
                        metric="cosine",
                        spec=spec,
                    )
                self.index = self.pc.Index(self._index_name)
                self.log.info("Pinecone connection established")
            except Exception as e:
                self.log.warning(f"Pinecone init failed: {e}")
                self.index = None

    def get_total_count(self) -> int:
        try:
            self._ensure_ready()
            if not self.index:
                return 0
            stats = self.index.describe_index_stats()
            return int(stats.get("total_vector_count", 0))
        except Exception:
            return 0

    def ensure_foundational_memories(self, memories: Optional[List[str]] = None):
        self._ensure_ready()
        if not self.index or not self.model:
            return
        try:
            stats = self.index.describe_index_stats()
            if stats.get("total_vector_count", 0) == 0:
                self.log.info("Pre-populating Pinecone with foundational memories …")
                vectors: List[Tuple[str, List[float], dict]] = []
                for i, text in enumerate(memories or FOUNDATIONAL_MEMORIES):
                    vec = self.model.encode(text).tolist()
                    meta = {"text": text, "timestamp": time.time(), "type": "foundational"}
                    vectors.append((str(i), vec, meta))
                self.index.upsert(vectors=vectors)
                self.log.info(f"Added {len(vectors)} foundational memories")
            else:
                self.log.info("Found existing memories, skipping pre-population")
        except Exception as e:
            self.log.warning(f"Foundational pre-population failed: {e}")

    def query_similar_texts(self, text: str, top_k: int = 3) -> List[str]:
        self._ensure_ready()
        if not text or not self.model or not self.index:
            return []
        try:
            vec = self.model.encode(text).tolist()
            res = self.index.query(vector=vec, top_k=top_k, include_metadata=True)
            return [m["metadata"]["text"] for m in res.get("matches", []) if m.get("metadata")]
        except Exception as e:
            self.log.warning(f"Memory query failed: {e}")
            return []

    def upsert_texts(self, texts: List[str]):
        self._ensure_ready()
        if not self.model or not self.index:
            return
        try:
            # Bufferize inputs for batch upserts
            for t in texts:
                if isinstance(t, str) and t.strip():
                    self._buffer.append(t)
            if len(self._buffer) >= self._batch_size:
                # flush
                base = self.get_total_count()
                to_write = self._buffer[: self._batch_size]
                self._buffer = self._buffer[self._batch_size:]
                vectors = []
                for i, text in enumerate(to_write):
                    vec = self.model.encode(text).tolist()
                    meta = {"text": text, "timestamp": time.time(), "type": "narrative"}
                    vectors.append((str(base + i), vec, meta))
                if vectors:
                    self.index.upsert(vectors=vectors)
        except Exception as e:
            self.log.warning(f"Upsert texts failed: {e}")

    def flush(self):
        self._ensure_ready()
        if not self.model or not self.index or not self._buffer:
            return
        try:
            base = self.get_total_count()
            vectors = []
            for i, text in enumerate(self._buffer):
                vec = self.model.encode(text).tolist()
                meta = {"text": text, "timestamp": time.time(), "type": "narrative"}
                vectors.append((str(base + i), vec, meta))
            if vectors:
                self.index.upsert(vectors=vectors)
            self._buffer = []
        except Exception as e:
            self.log.warning(f"Flush failed: {e}")
