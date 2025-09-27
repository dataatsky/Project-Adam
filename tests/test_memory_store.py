from collections import defaultdict
import sys

import services.memory_store as memory_store


def test_memory_store_uses_model_dimension_and_environment(monkeypatch):
    recorded = defaultdict(list)

    class FakeModel:
        def get_sentence_embedding_dimension(self):
            return 768

        def encode(self, text):
            class _Vec:
                def tolist(self):
                    return [0.1] * 768

            return _Vec()

    def fake_sentence_transformer(name):
        recorded["model_name"] = name
        return FakeModel()

    monkeypatch.setattr(memory_store, "SentenceTransformer", fake_sentence_transformer)

    class FakeServerlessSpec:
        def __init__(self, cloud, region):
            recorded["spec_args"] = (cloud, region)
            self.cloud = cloud
            self.region = region

    monkeypatch.setattr(memory_store, "ServerlessSpec", FakeServerlessSpec)

    class FakeIndex:
        def describe_index_stats(self):
            return {"total_vector_count": 0}

        def upsert(self, *args, **kwargs):
            vectors = kwargs.get("vectors")
            recorded["upsert"].append(vectors)

    class FakePinecone:
        def __init__(self, api_key):
            recorded["api_key"] = api_key

        def list_indexes(self):
            class _List:
                @staticmethod
                def names():
                    return []

            return _List()

        def create_index(self, **kwargs):
            recorded["create"].append(kwargs)

        def Index(self, name):
            recorded["index_name"] = name
            return FakeIndex()

    monkeypatch.setattr(memory_store, "Pinecone", FakePinecone)

    store = memory_store.MemoryStore(
        api_key="test-key",
        environment="us-west1-gcp",
        index_name="adam-memory",
        model_name="all-mpnet-base-v2",
        cloud=None,
        region=None,
        batch_size=1,
        backend="pinecone",
    )

    store.ensure_foundational_memories(["memory"])

    assert recorded["api_key"] == "test-key"
    assert recorded["spec_args"] == ("gcp", "us-west1")
    assert recorded["create"][0]["dimension"] == 768
    assert store.dimension == 768
    vectors = recorded["upsert"][0]
    assert len(vectors[0][1]) == 768


def test_memory_store_chroma_backend(monkeypatch, tmp_path):
    recorded = defaultdict(list)

    class FakeModel:
        def get_sentence_embedding_dimension(self):
            return 512

        def encode(self, text):
            class _Vec:
                def tolist(self):
                    return [0.2] * 512

            return _Vec()

    def fake_sentence_transformer(name):
        recorded["model_name"] = name
        return FakeModel()

    monkeypatch.setattr(memory_store, "SentenceTransformer", fake_sentence_transformer)

    class FakeCollection:
        def __init__(self):
            self.docs = []

        def count(self):
            return len(self.docs)

        def upsert(self, ids, embeddings, documents, metadatas):
            recorded["upsert"].append({
                "ids": ids,
                "documents": documents,
                "metadatas": metadatas,
            })
            for doc in documents:
                self.docs.append(doc)

        def query(self, query_embeddings, n_results):
            return {"documents": [self.docs[:n_results]]}

    class FakeClient:
        def __init__(self, path):
            recorded["chroma_path"] = path
            self.collection = FakeCollection()

        def get_or_create_collection(self, name, metadata=None):
            recorded["collection_name"] = name
            recorded["collection_metadata"] = metadata
            return self.collection

    fake_module = type("FakeChromadb", (), {"PersistentClient": FakeClient})
    monkeypatch.setitem(sys.modules, "chromadb", fake_module)

    store = memory_store.MemoryStore(
        api_key=None,
        environment=None,
        index_name="adam-memory",
        model_name="all-mpnet-base-v2",
        backend="chroma",
        chroma_path=str(tmp_path / "chroma"),
        batch_size=1,
    )

    store.ensure_foundational_memories(["foundational"])
    store.upsert_texts(["hello world"])
    store.flush()

    res = store.query_similar_texts("hello", top_k=1)
    if res:
        assert res[0] in {"foundational", "hello world"}
    assert recorded["collection_name"] == "adam-memory"
    assert recorded["model_name"] == "all-mpnet-base-v2"
