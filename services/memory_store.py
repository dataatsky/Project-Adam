import time
from typing import List, Tuple, Optional

from sentence_transformers import SentenceTransformer
from pinecone import Pinecone


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

    def __init__(self, *, api_key: Optional[str], environment: Optional[str], index_name: Optional[str], model_name: Optional[str], dimension: int = 384):
        self.model = None
        self.pc = None
        self.index = None
        self.dimension = dimension
        # Model
        try:
            if model_name:
                self.model = SentenceTransformer(model_name)
        except Exception as e:
            print(f"⚠️ SentenceTransformer init failed: {e}")
            self.model = None
        # Pinecone
        try:
            if api_key and environment and index_name:
                self.pc = Pinecone(api_key=api_key, environment=environment)
                try:
                    # New SDK returns an IndexList object with .names()
                    indexes = self.pc.list_indexes().names()
                except Exception:
                    indexes = self.pc.list_indexes()
                if index_name not in indexes:
                    print(f"Creating Pinecone index: {index_name}")
                    self.pc.create_index(name=index_name, dimension=self.dimension, metric="cosine")
                self.index = self.pc.Index(index_name)
                print("Pinecone connection established.")
        except Exception as e:
            print(f"⚠️ Pinecone init failed: {e}")
            self.index = None

    def get_total_count(self) -> int:
        try:
            if not self.index:
                return 0
            stats = self.index.describe_index_stats()
            return int(stats.get("total_vector_count", 0))
        except Exception:
            return 0

    def ensure_foundational_memories(self, memories: Optional[List[str]] = None):
        if not self.index or not self.model:
            return
        try:
            stats = self.index.describe_index_stats()
            if stats.get("total_vector_count", 0) == 0:
                print("— Pre-populating Pinecone with foundational memories …")
                vectors: List[Tuple[str, List[float], dict]] = []
                for i, text in enumerate(memories or FOUNDATIONAL_MEMORIES):
                    vec = self.model.encode(text).tolist()
                    meta = {"text": text, "timestamp": time.time(), "type": "foundational"}
                    vectors.append((str(i), vec, meta))
                self.index.upsert(vectors=vectors)
                print(f"— Added {len(vectors)} foundational memories.")
            else:
                print("— Found existing memories, skipping pre-population.")
        except Exception as e:
            print(f"⚠️ Foundational pre-population failed: {e}")

    def query_similar_texts(self, text: str, top_k: int = 3) -> List[str]:
        if not text or not self.model or not self.index:
            return []
        try:
            vec = self.model.encode(text).tolist()
            res = self.index.query(vector=vec, top_k=top_k, include_metadata=True)
            return [m["metadata"]["text"] for m in res.get("matches", []) if m.get("metadata")]
        except Exception as e:
            print(f"⚠️ Memory query failed: {e}")
            return []

    def upsert_texts(self, texts: List[str]):
        if not self.model or not self.index:
            return
        try:
            base = self.get_total_count()
            vectors = []
            for i, text in enumerate(texts):
                vec = self.model.encode(text).tolist()
                meta = {"text": text, "timestamp": time.time(), "type": "narrative"}
                vectors.append((str(base + i), vec, meta))
            if vectors:
                self.index.upsert(vectors=vectors)
        except Exception as e:
            print(f"⚠️ Upsert texts failed: {e}")

