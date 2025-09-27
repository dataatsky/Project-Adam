import time
import uuid
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
    """Wrapper around SentenceTransformer + vector store (Chroma or Pinecone).

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
        backend: str = "chroma",
        chroma_path: Optional[str] = None,
        chroma_collection: Optional[str] = None,
    ):
        self.log = logging.getLogger(__name__ + ".MemoryStore")
        self.model = None
        self.pc = None
        self.index = None
        self.dimension = dimension
        self._batch_size = int(batch_size)
        self._buffer: List[str] = []
        self._backend = (backend or "chroma").strip().lower()

        # Defer heavy init until first use
        self._api_key = api_key
        self._env = environment
        self._index_name = index_name or "adam-memory"
        self._model_name = model_name
        self._cloud = (cloud or "").strip() or None
        self._region = (region or "").strip() or None
        if (not self._cloud or not self._region) and self._env:
            inferred = _parse_environment(self._env)
            self._cloud = self._cloud or inferred[0]
            self._region = self._region or inferred[1]

        # Chroma specific fields
        self._chroma_path = chroma_path or "./chroma"
        self._chroma_collection = chroma_collection or self._index_name
        self._chroma_client = None
        self._chroma_collection_handle = None

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
        if self._backend == "pinecone":
            self._ensure_pinecone_ready()
        elif self._backend == "chroma":
            self._ensure_chroma_ready()
        else:
            if not hasattr(self, "_backend_warned"):
                self.log.warning(f"Unknown memory backend '{self._backend}'. Falling back to no-op store.")
                self._backend_warned = True

    def _ensure_pinecone_ready(self):
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

    def _ensure_chroma_ready(self):
        if self._chroma_collection_handle is not None:
            return
        try:
            import chromadb

            if self._chroma_client is None:
                self._chroma_client = chromadb.PersistentClient(path=self._chroma_path)
            metadata = {"hnsw:space": "cosine"}
            self._chroma_collection_handle = self._chroma_client.get_or_create_collection(
                name=self._chroma_collection,
                metadata=metadata,
            )
            self.log.info("Chroma collection ready at %s", self._chroma_path)
        except Exception as e:
            self.log.warning(f"Chroma init failed: {e}")
            self._chroma_collection_handle = None

    def get_total_count(self) -> int:
        try:
            self._ensure_ready()
            if self._backend == "pinecone" and self.index:
                stats = self.index.describe_index_stats()
                return int(stats.get("total_vector_count", 0))
            if self._backend == "chroma" and self._chroma_collection_handle:
                return int(self._chroma_collection_handle.count())
            return 0
        except Exception:
            return 0

    def ensure_foundational_memories(self, memories: Optional[List[str]] = None):
        self._ensure_ready()
        if not self.model:
            return
        try:
            memories = memories or FOUNDATIONAL_MEMORIES
            if self._backend == "pinecone" and self.index:
                stats = self.index.describe_index_stats()
                if stats.get("total_vector_count", 0) == 0:
                    self.log.info("Pre-populating Pinecone with foundational memories …")
                    vectors: List[Tuple[str, List[float], dict]] = []
                    for i, text in enumerate(memories):
                        vec = self.model.encode(text).tolist()
                        meta = {"text": text, "timestamp": time.time(), "type": "foundational"}
                        vectors.append((str(i), vec, meta))
                    if vectors:
                        self.index.upsert(vectors=vectors)
                        self.log.info(f"Added {len(vectors)} foundational memories")
                else:
                    self.log.info("Found existing memories, skipping pre-population")
            elif self._backend == "chroma" and self._chroma_collection_handle:
                if self._chroma_collection_handle.count() == 0:
                    self.log.info("Pre-populating Chroma with foundational memories …")
                    self._write_chroma_batch(memories, memory_type="foundational")
                else:
                    self.log.info("Found existing Chroma memories, skipping pre-population")
        except Exception as e:
            self.log.warning(f"Foundational pre-population failed: {e}")

    def query_similar_texts(self, text: str, top_k: int = 3) -> List[str]:
        self._ensure_ready()
        if not text or not self.model:
            return []
        try:
            vec = self.model.encode(text).tolist()
            if self._backend == "pinecone" and self.index:
                res = self.index.query(vector=vec, top_k=top_k, include_metadata=True)
                return [m["metadata"]["text"] for m in res.get("matches", []) if m.get("metadata")]
            if self._backend == "chroma" and self._chroma_collection_handle:
                result = self._chroma_collection_handle.query(query_embeddings=[vec], n_results=top_k)
                documents = result.get("documents") or []
                if documents:
                    return [doc for doc in documents[0] if doc]
            return []
        except Exception as e:
            self.log.warning(f"Memory query failed: {e}")
            return []

    def upsert_texts(self, texts: List[str]):
        self._ensure_ready()
        if not self.model:
            return
        try:
            # Bufferize inputs for batch upserts
            for t in texts:
                if isinstance(t, str) and t.strip():
                    self._buffer.append(t)
            if len(self._buffer) >= self._batch_size:
                to_write = self._buffer[: self._batch_size]
                self._buffer = self._buffer[self._batch_size:]
                self._write_batch(to_write)
        except Exception as e:
            self.log.warning(f"Upsert texts failed: {e}")

    def flush(self):
        self._ensure_ready()
        if not self.model or not self._buffer:
            return
        try:
            self._write_batch(self._buffer)
            self._buffer = []
        except Exception as e:
            self.log.warning(f"Flush failed: {e}")

    # ------------------------------------------------------------------
    def _write_batch(self, texts: List[str]):
        if not texts:
            return
        if self._backend == "pinecone" and self.index:
            self._write_pinecone_batch(texts)
        elif self._backend == "chroma" and self._chroma_collection_handle:
            self._write_chroma_batch(texts)

    def _write_pinecone_batch(self, texts: List[str], memory_type: str = "narrative"):
        base = self.get_total_count()
        vectors = []
        for i, text in enumerate(texts):
            vec = self.model.encode(text).tolist()
            meta = {"text": text, "timestamp": time.time(), "type": memory_type}
            vectors.append((str(base + i), vec, meta))
        if vectors:
            self.index.upsert(vectors=vectors)

    def _write_chroma_batch(self, texts: List[str], memory_type: str = "narrative"):
        ids = [str(uuid.uuid4()) for _ in texts]
        embeddings = [self.model.encode(text).tolist() for text in texts]
        metadatas = [{"timestamp": time.time(), "type": memory_type} for _ in texts]
        self._chroma_collection_handle.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
        )
