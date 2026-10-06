from dataclasses import asdict
import json
from unittest.mock import Mock
from fastapi.testclient import TestClient
from server import api
from server.hybrid_search import service
from server.search_engine.BM25 import build_bm25_index
from server.semantic_search.search import SemanticSearchResult


def test_pipeline_order_metadata_document_view_and_failures(monkeypatch):
    documents = {"local.txt": "replication notes", "web": "sharding page"}
    monkeypatch.setattr(api.state, "file_data", documents)
    monkeypatch.setattr(api.state, "metadata", {"web": {"title": "Guide", "url": "https://example.com", "source": "mdn", "domain": "example.com"}})
    monkeypatch.setattr(api.state, "bm25_index", build_bm25_index(documents))
    monkeypatch.setattr(api.state, "client", object())
    semantic = Mock(return_value=[SemanticSearchResult("web", "chunk1", "sharding page", .8)])
    monkeypatch.setattr(service, "semantic_search", semantic)
    def fake_rerank(query, hits, **kwargs):
        return [{**kwargs["document_metadata"][h.document_name], **asdict(h),
                 "text": h.text or documents[h.document_name], "reranker_score": 5.0-i}
                for i, h in enumerate(reversed(hits))][:kwargs["top_k"]]
    reranker = Mock(side_effect=fake_rerank)
    monkeypatch.setattr(service, "rerank", reranker)
    client = TestClient(api.app)
    response = client.get("/api/search", params={"q": "replication", "top_k": 2, "candidate_k": 5, "semantic_k": 40})
    assert response.status_code == 200
    data = response.json()
    assert data["pipeline"] == "hybrid_rrf_reranker"
    assert [r["file_name"] for r in data["results"]] == ["web", "local.txt"]
    hit = data["results"][0]
    assert hit["url"] == "https://example.com" and hit["title"] == "Guide"
    assert hit["source"] == "mdn" and hit["domain"] == "example.com"
    assert hit["chunk_id"] == "chunk1" and hit["semantic_score"] == .8
    assert hit["score"] == hit["reranker_score"] == 5
    assert semantic.call_args.kwargs["top_k"] == 40
    assert reranker.call_args.kwargs["candidate_k"] == 5
    assert client.get("/api/document", params={"file_name": "web"}).json()["text"] == "sharding page"
    assert client.get("/api/search", params={"q": "x", "top_k": 0}).status_code == 422
    assert client.get("/api/search", params={"q": "x", "candidate_k": 1}).status_code == 400
    semantic.return_value = [SemanticSearchResult("missing", "id", "text", 1)]
    assert client.get("/api/search", params={"q": "zzzz"}).json()["results"] == []
    semantic.side_effect = RuntimeError("secret error")
    response = client.get("/api/search", params={"q": "replication"})
    assert response.status_code == 503 and "secret" not in response.text


def test_startup_corpus_merge_and_client_lifecycle(monkeypatch, tmp_path):
    (tmp_path / "local.txt").write_text("local text")
    manifest = tmp_path / "index.json"
    manifest.write_text(json.dumps({"documents": {"https://example.com": {
        "document_name": "web", "text": "page text", "chunks": [{"title": "Guide"}]}}}))
    monkeypatch.setattr(api, "DATA_DIR", tmp_path)
    monkeypatch.setattr(service, "DEFAULT_INDEX_FILE", manifest)
    monkeypatch.setattr(api, "state", api.EngineState())
    fake = Mock()
    connect = Mock(return_value=(fake, "collection"))
    monkeypatch.setattr(api, "connect_qdrant", connect)
    with TestClient(api.app) as client:
        assert client.get("/api/health").json()["documents"] == 2
        assert api.state.metadata["web"]["title"] == "Guide"
    connect.assert_called_once()
    fake.close.assert_called_once()
