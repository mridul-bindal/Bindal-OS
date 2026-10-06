import pytest
from evaluation.rerank import compare


@pytest.mark.parametrize("values,ranking,category", [
    ((1, 1, 1), ["b", "a"], "improved"),
    ((0, 1, .25), ["b", "a"], "decreased"),
    ((1, 1, .25), ["b", "a"], "mixed"),
    ((.5, 1, .5), ["b", "a"], "changed_without_metric_gain"),
    ((.5, 1, .5), ["a", "b"], "unchanged"),
])
def test_classification_uses_metrics_not_scores(values, ranking, category):
    keys = ("recall_at_5", "recall_at_10", "reciprocal_rank")
    before = {"ranking": ["a", "b"], "metrics": dict(zip(keys, (.5, 1, .5)))}
    after = {"ranking": ranking, "metrics": dict(zip(keys, values))}
    assert compare(before, after)["category"] == category
