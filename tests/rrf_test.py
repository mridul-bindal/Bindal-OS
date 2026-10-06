from types import SimpleNamespace
import pytest
from server.hybrid_search import aggregate_semantic_results, reciprocal_rank_fusion


def bm(*names):
    return [{"file_name": name, "score": 100 - i} for i, name in enumerate(names)]


def sem(*names):
    return [SimpleNamespace(document_name=name, chunk_id=f"{name}-{i}",
                            text=f"text {i}", score=1 - i / 100)
            for i, name in enumerate(names)]


def test_overlap_single_source_scores_and_ranking():
    results = reciprocal_rank_fusion(bm("a", "b"), sem("b", "c"))
    assert [r.document_name for r in results] == ["b", "a", "c"]
    b, a, c = results
    assert b.rrf_score == pytest.approx(1 / 62 + 1 / 61)
    assert a.rrf_score == pytest.approx(1 / 61)
    assert c.rrf_score == pytest.approx(1 / 62)
    assert (b.bm25_rank, b.semantic_rank, b.bm25_score) == (2, 1, 99)
    assert (b.chunk_id, b.text, b.semantic_score) == ("b-0", "text 0", 1)
    assert a.chunk_id is a.text is a.semantic_score is a.semantic_rank is None
    assert c.bm25_rank is c.bm25_score is None


@pytest.mark.parametrize("k", [0, 1, 10.5, 100])
def test_configurable_k(k):
    result = reciprocal_rank_fusion(bm("a"), sem("a"), k=k)[0]
    assert result.rrf_score == pytest.approx(2 / (k + 1))


def test_duplicates_do_not_add_votes_or_penalize_other_documents():
    chunks = sem("a", "a", "a", "b", "b")
    assert [r.document_name for r in aggregate_semantic_results(chunks)] == ["a", "b"]
    result = reciprocal_rank_fusion(bm("a", "a", "b"), chunks)
    baseline = reciprocal_rank_fusion(bm("a", "b"), sem("a", "b"))
    assert [r.rrf_score for r in result] == [r.rrf_score for r in baseline]
    assert result[0].chunk_id == "a-0"
    assert result[1].chunk_id == "b-3"
    assert result[1].semantic_rank == result[1].bm25_rank == 2
    assert len(chunks) == 5


@pytest.mark.parametrize("b,s,expected", [([], [], []), (bm("b", "a"), [], ["b", "a"]),
                                         ([], sem("a", "b"), ["a", "b"])])
def test_empty_sources(b, s, expected):
    assert [r.document_name for r in reciprocal_rank_fusion(b, s)] == expected


def test_ties_are_deterministic_and_raw_scores_do_not_affect_fusion():
    b, s = bm("b", "a"), sem("a", "b")
    before = reciprocal_rank_fusion(b, s)
    b[0]["score"] = 100000
    assert [r.document_name for r in before] == ["a", "b"]
    assert [r.rrf_score for r in reciprocal_rank_fusion(b, s)] == [r.rrf_score for r in before]


@pytest.mark.parametrize("k", [-1, float("inf"), float("nan"), True, "60"])
def test_invalid_k(k):
    with pytest.raises(ValueError, match="k must"):
        reciprocal_rank_fusion([], [], k=k)
