from contextlib import closing
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from qdrant_client import QdrantClient, models

from server.semantic_search import search


def vector(first=1.0, second=0.0):
    return [first, second] + [0.0] * 382


def encoder(values=None):
    return Mock(encode=Mock(return_value=[vector()] if values is None else values))


def test_query_reuses_cached_model_and_client_and_maps_results(monkeypatch):
    model = encoder()
    monkeypatch.setattr(search, "get_embedding_model", lambda: model)
    client = Mock()
    client.query_points.return_value = SimpleNamespace(points=[SimpleNamespace(
        id=1, payload={"document_name": "index.txt", "chunk_id": "index.txt::chunk-0",
                       "text": "An index speeds up queries."}, score=0.9)])
    for _ in range(2):
        results = search.semantic_search("  How can I speed up queries?  ", client=client, top_k=2)
    assert results == [search.SemanticSearchResult(
        "index.txt", "index.txt::chunk-0", "An index speeds up queries.", 0.9)]
    model.encode.assert_called_with(["How can I speed up queries?"])
    assert client.query_points.call_count == 2
    client.query_points.assert_called_with(
        collection_name="bindal_document_chunks", query=vector(), limit=2,
        with_payload=["document_name", "chunk_id", "text", "source", "domain"], with_vectors=False)
    client.close.assert_not_called()
    client.create_collection.assert_not_called()


@pytest.mark.parametrize("query,top_k", [("", 5), (" \n", 5), (None, 5),
                                           ("query", 0), ("query", -1),
                                           ("query", True), ("query", 1.5)])
def test_invalid_input_does_not_encode_or_search(query, top_k):
    client, model = Mock(), encoder()
    with pytest.raises(ValueError):
        search.semantic_search(query, client=client, model=model, top_k=top_k)
    model.encode.assert_not_called()
    client.query_points.assert_not_called()


@pytest.mark.parametrize("values", [[], [vector(), vector()], [[1.0] * 10],
                                     [[0.0] * 384], [vector(float("nan"))],
                                     [vector(float("inf"))]])
def test_invalid_embedding_does_not_search(values):
    client = Mock()
    with pytest.raises(ValueError):
        search.semantic_search("MongoDB", client=client, model=encoder(values))
    client.query_points.assert_not_called()


def test_real_qdrant_ranking_top_k_and_empty_collection():
    with closing(QdrantClient(":memory:")) as client:
        client.create_collection("test", vectors_config=models.VectorParams(
            size=384, distance=models.Distance.COSINE))
        def run(top_k):
            return search.semantic_search("MongoDB", client=client, collection="test",
                                          model=encoder(), top_k=top_k)
        assert run(5) == []
        client.upsert("test", points=[models.PointStruct(
            id=i, vector=v, payload={"document_name": f"{i}.txt",
                                     "chunk_id": str(i), "text": f"Chunk {i}"})
            for i, v in [(1, vector(0, 1)), (2, vector()), (3, vector(1, 1))]])
        assert [r.chunk_id for r in run(2)] == ["2", "3"]
        results = run(10)
        assert len(results) == 3
        assert [r.score for r in results] == pytest.approx([1, 2**-0.5, 0])
        assert client.count("test").count == 3


def test_backend_error_is_not_hidden():
    client = Mock()
    client.query_points.side_effect = RuntimeError("Qdrant unavailable")
    with pytest.raises(RuntimeError, match="Qdrant unavailable"):
        search.semantic_search("MongoDB", client=client, model=encoder())


def test_malformed_payload_is_reported():
    client = Mock()
    client.query_points.return_value = SimpleNamespace(points=[SimpleNamespace(id=1, payload={})])
    with pytest.raises(ValueError, match="required chunk metadata"):
        search.semantic_search("MongoDB", client=client, model=encoder())
