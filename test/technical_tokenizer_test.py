import pytest
from server.search_engine.tokenizer import tokenize
from server.search_engine.BM25 import build_bm25_index, search_bm25_index


@pytest.mark.parametrize("compact,variant", [("MongoDB", "mongo DB"), ("RedisCache", "redis cache"),
    ("VectorStore", "vector store"), ("OpenSearch", "open search"), ("Node.js", "node js"),
    ("React.js", "react js"), ("machine-learning", "machine learning"), ("shard-key", "shard key"),
    ("user_name", "user name")])
def test_general_variants_match_both_indexing_directions(compact, variant):
    for doc_text, query in ((compact, variant), (variant, compact), (compact.lower(), variant.upper())):
        index = build_bm25_index({"relevant": doc_text, "unrelated": "elephant habitat"})
        hits = search_bm25_index(query, index)
        assert hits and hits[0]["file_name"] == "relevant"


@pytest.mark.parametrize("term", ["MongoDB", "Node.js", ".NET", "C++", "C#", "$lookup", "$group", "shard-key", "HTTPServer"])
def test_case_variants_have_identical_representations(term):
    assert tokenize(term) == tokenize(term.lower()) == tokenize(term.upper())


def test_meaningful_punctuation_not_destroyed():
    for term in ("C++", "C#", "$lookup", "$group", ".NET", "Node.js", "shard-key", "1.2"):
        assert term.lower() in tokenize(term)
    for a, b in (("C++", "C#"), ("C++", "C"), ("$lookup", "lookup"), (".NET", "net"), ("1.2", "12")):
        assert not set(tokenize(a)) & set(tokenize(b))


def test_no_alias_across_sentence_or_line_or_stopwords():
    for text in ("vector, store", "vector\nstore", "vector; store", "vector and store"):
        assert "vectorstore" not in tokenize(text)


def test_mongodb_variants_have_same_hits():
    index = build_bm25_index({"one": "MongoDB replication", "two": "MONGODB sharding", "other": "unrelated content"})
    results = [search_bm25_index(q, index) for q in ("MongoDB", "mongo DB", "mongodb")]
    assert results[0] == results[1] == results[2]


def test_api_uses_same_query_representation_as_direct_bm25(monkeypatch):
    from dataclasses import asdict
    from fastapi.testclient import TestClient
    from server.api import app, state
    documents = {"compound": "vectorstore", "phrase": "vector and store"}
    index = build_bm25_index(documents)
    monkeypatch.setattr(state, "file_data", documents)
    monkeypatch.setattr(state, "bm25_index", index)
    monkeypatch.setattr(state, "client", object())
    monkeypatch.setattr("server.hybrid_search.service.semantic_search", lambda *a, **kw: [])
    monkeypatch.setattr("server.hybrid_search.service.rerank", lambda query, hits, **kw: [
        {**asdict(hit), "text": documents[hit.document_name], "reranker_score": 1.0} for hit in hits])
    response = TestClient(app).get("/api/search", params={"q": "vector and store"})
    assert response.status_code == 200
    assert [r["file_name"] for r in response.json()["results"]] == [
        r["file_name"] for r in search_bm25_index("vector and store", index)]
