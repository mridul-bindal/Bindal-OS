from contextlib import closing
import pytest
from qdrant_client import QdrantClient, models

from server.semantic_search.embeddings import EmbeddedChunk
from server.semantic_search.vector_store import ensure_collection, store_chunks
from server.semantic_search import vector_store, build_embeddings


def chunk(name, number=0):
    return EmbeddedChunk(name, f"{name}::chunk-{number}", "Original text", [0.1] * 384)


def test_store_roundtrip_and_rebuild_removes_stale_chunks_only_in_source():
    with closing(QdrantClient(":memory:")) as client:
        def save(chunks, source="test"):
            return store_chunks(client, "chunks", chunks, source=source,
                                chunk_words=250, overlap_words=40, batch_size=1)

        save([chunk("other.txt")], "other")
        assert save([chunk("a.txt"), chunk("a.txt", 1), chunk("deleted.txt")]) == 3
        first, _ = client.scroll("chunks", limit=10)
        original_id = next(p.id for p in first if p.payload["chunk_id"] == "a.txt::chunk-0")
        save([chunk("a.txt")])
        points, _ = client.scroll("chunks", with_vectors=True)
        assert len(points) == 2
        point = next(p for p in points if p.payload["source"] == "test")
        assert point.id == original_id
        assert point.payload["text"] == "Original text"
        assert len(point.vector) == 384
        assert client.query_points("chunks", query=[0.1] * 384, limit=1).points


def test_reject_incompatible_collection_without_recreating():
    with closing(QdrantClient(":memory:")) as client:
        client.create_collection("chunks", vectors_config=models.VectorParams(
            size=10, distance=models.Distance.COSINE))
        with pytest.raises(ValueError, match="384"):
            ensure_collection(client, "chunks")
        assert client.get_collection("chunks").config.params.vectors.size == 10


def test_failed_upload_does_not_delete_existing_chunks(monkeypatch):
    with closing(QdrantClient(":memory:")) as client:
        store_chunks(client, "chunks", [chunk("old.txt")], source="test",
                     chunk_words=250, overlap_words=40)
        def fail(**kwargs):
            raise RuntimeError("upload failed")
        monkeypatch.setattr(client, "upsert", fail)
        with pytest.raises(RuntimeError, match="upload failed"):
            store_chunks(client, "chunks", [chunk("new.txt")], source="test",
                         chunk_words=250, overlap_words=40)
        assert client.count("chunks").count == 1


def test_config_loads_adjacent_env_and_preserves_environment(monkeypatch, tmp_path):
    env = tmp_path / ".env"
    env.write_text("QDRANT_URL=https://example.invalid\nQDRANT_API_KEY=test-key\nQDRANT_COLLECTION=from-file\n")
    monkeypatch.setattr(vector_store, "ENV_FILE", env)
    for key in ("QDRANT_URL", "QDRANT_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("QDRANT_COLLECTION", "from-environment")
    captured = {}
    monkeypatch.setattr(vector_store, "QdrantClient", lambda **kwargs: captured.update(kwargs))
    _, collection = vector_store.connect_qdrant()
    assert collection == "from-environment"
    assert captured["url"] == "https://example.invalid"
    assert captured["api_key"] == "test-key"


def test_builder_uses_original_chunks_and_database(monkeypatch, tmp_path):
    (tmp_path / "a.txt").write_text("One two three four five", encoding="utf-8")
    client = QdrantClient(":memory:")
    monkeypatch.setattr(build_embeddings, "connect_qdrant", lambda: (client, "chunks"))
    monkeypatch.setattr(client, "close", lambda: None)
    monkeypatch.setattr(build_embeddings, "embed_chunks", lambda chunks: [
        EmbeddedChunk(c.document_name, c.chunk_id, c.text, [0.1] * 384) for c in chunks
    ])
    try:
        assert build_embeddings.build_embedding_database(tmp_path, chunk_words=3, overlap_words=1) == 2
        points, _ = client.scroll("chunks")
        assert {p.payload["text"] for p in points} == {"One two three", "three four five"}
        assert not list(tmp_path.glob("*.json"))
    finally:
        QdrantClient.close(client)

