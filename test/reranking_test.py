from unittest.mock import Mock
import sys
from types import SimpleNamespace

import pytest

from server.hybrid_search.rrf import reciprocal_rank_fusion
from server.reranking import get_reranker_model, rerank


def candidates():
    return [{"document_name": str(i), "chunk_id": f"chunk-{i}", "text": f"text {i}",
             "source_url": f"https://example.com/{i}", "rrf_score": 0.03,
             "bm25_score": 10, "semantic_score": 0.8} for i in range(3)]


def test_pairs_order_limits_and_metadata():
    model = Mock(predict=Mock(return_value=[0.2, 0.9]))
    original = candidates()
    results = rerank("query", original, candidate_k=2, top_k=1, model=model)
    model.predict.assert_called_once_with([("query", "text 0"), ("query", "text 1")], show_progress_bar=False)
    assert results == [{**original[1], "reranker_score": 0.9}]
    assert "reranker_score" not in original[1]


def test_empty_does_not_load_model(monkeypatch):
    loader = Mock()
    monkeypatch.setattr("server.reranking.reranker.get_reranker_model", loader)
    assert rerank("query", []) == []
    loader.assert_not_called()


def test_real_rrf_objects_and_bm25_only_text_enrichment():
    fused = reciprocal_rank_fusion([{"file_name": "a", "score": 3}], [])
    results = rerank("query", fused, model=Mock(predict=Mock(return_value=[1])),
                     document_metadata={"a": {"text": "Full document", "url": "https://example.com"}})
    assert results[0]["text"] == "Full document"
    assert results[0]["url"] == "https://example.com"
    assert results[0]["bm25_score"] == 3
    assert results[0]["rrf_score"] == fused[0].rrf_score
    assert results[0]["chunk_id"] is None
    assert fused[0].text is None
    with pytest.raises(ValueError, match="Missing candidate text"):
        rerank("query", fused)


def test_model_cache_and_model_name(monkeypatch):
    factory = Mock(side_effect=lambda *a, **kw: object())
    monkeypatch.setitem(sys.modules, "sentence_transformers", SimpleNamespace(CrossEncoder=factory))
    get_reranker_model.cache_clear()
    try:
        first = get_reranker_model("one")
        assert get_reranker_model("one") is first
        assert get_reranker_model("two") is not first
        assert factory.call_count == 2
        factory.assert_called_with("two", max_length=512)
    finally:
        get_reranker_model.cache_clear()


def test_ties_preserve_rrf_order_and_top_k_can_exceed_pool():
    results = rerank("query", candidates(), top_k=10, model=Mock(predict=Mock(return_value=[1, 1, -1])))
    assert [r["document_name"] for r in results] == ["0", "1", "2"]


@pytest.mark.parametrize("kwargs", [{"candidate_k": 0}, {"top_k": -1}, {"top_k": True}, {"candidate_k": 1.5}])
def test_invalid_limits(kwargs):
    with pytest.raises(ValueError):
        rerank("query", [], **kwargs)


@pytest.mark.parametrize("scores", [[1], [1, 2, float("nan")]])
def test_bad_scores(scores):
    with pytest.raises(ValueError):
        rerank("query", candidates(), model=Mock(predict=Mock(return_value=scores)))
