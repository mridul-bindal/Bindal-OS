import pytest
from evaluation.evaluate import retrieval_metrics


def test_metrics_use_all_relevant_documents_and_first_relevant_rank():
    scores = retrieval_metrics(["a", "b", "c", "d", "e", "f", "g"], {"b", "g", "missing"})
    assert scores == pytest.approx({"recall_at_5": 1 / 3, "recall_at_10": 2 / 3, "reciprocal_rank": 1 / 2})


def test_metric_deduplication_and_missing_results():
    assert retrieval_metrics(["a", "a", "b"], {"b"})["reciprocal_rank"] == 0.5
    assert retrieval_metrics([], {"b"}) == {"recall_at_5": 0, "recall_at_10": 0, "reciprocal_rank": 0}
    with pytest.raises(ValueError):
        retrieval_metrics(["a"], set())


def test_reciprocal_rank_is_not_truncated_at_ten():
    ranking = [str(i) for i in range(11)]
    assert retrieval_metrics(ranking, {"10"}) == pytest.approx({
        "recall_at_5": 0, "recall_at_10": 0, "reciprocal_rank": 1 / 11})
