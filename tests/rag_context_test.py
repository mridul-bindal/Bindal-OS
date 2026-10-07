from copy import deepcopy
import json

import pytest

from server.ai.rag import build_context


def hit(name="a", **overrides):
    return {"document_name": name, "chunk_id": f"{name}-1", "text": f"Text for {name}.",
            "title": f"Title {name}", "url": f"https://example.com/{name}",
            "domain": "example.com", "source": "mdn", "bm25_score": 2.0,
            "semantic_score": 0.7, "rrf_score": 0.03, "reranker_score": -1.0,
            **overrides}


def test_empty_results():
    context = build_context("original query", [])
    assert context.chunks == ()
    assert context.to_prompt_inputs() == {"query": "original query", "context": ""}
    assert context.to_dict()["chunks"] == []


def test_top_k_preserves_input_order_not_score_sorting():
    results = [hit("b"), hit("a", reranker_score=10), hit("c")]
    context = build_context("query", results, top_k=2)
    assert [c.document_name for c in context.chunks] == ["b", "a"]
    assert [c.rank for c in context.chunks] == [1, 2]
    assert len(build_context("query", results, top_k=20).chunks) == 3


def test_deduplication_before_limit_preserves_original_rank():
    results = [hit(), hit(chunk_id="a-2", text="Other chunk"),
               hit("alias", url="https://example.com/a"), hit("copy", text="Text for a."), hit("b")]
    context = build_context("query", results, top_k=2)
    assert [c.document_name for c in context.chunks] == ["a", "b"]
    assert [c.rank for c in context.chunks] == [1, 5]
    assert [c.source_id for c in context.chunks] == [1, 2]


def test_optional_multiple_chunks_still_removes_repeated_chunk_ids():
    context = build_context("query", [hit(), hit(text="Repeated ID"),
        hit(chunk_id="a-2", text="Distinct chunk"), hit("b", chunk_id="a-1")],
        deduplicate_documents=False)
    assert [c.rank for c in context.chunks] == [1, 3, 4]


def test_metadata_scores_text_query_and_inputs_preserved():
    results = [hit(text="def run():\n    return 1\n", title="Original title")]
    before = deepcopy(results)
    context = build_context("  Original query?  ", results)
    record = context.to_dict()["chunks"][0]
    assert all(record[key] == value for key, value in results[0].items())
    assert context.query == "  Original query?  "
    assert results == before
    assert json.loads(json.dumps(context.to_dict())) == context.to_dict()


def test_deterministic_format_and_contiguous_source_labels():
    results = [hit(), hit(), hit("b")]
    first = build_context("query", results)
    assert first == build_context("query", results)
    assert first.format_context() == build_context("query", results).format_context()
    assert first.format_context().startswith(
        "[Source 1]\nTitle: Title a\nDocument: a\nSource: mdn\nDomain: example.com\n"
        "URL: https://example.com/a\nChunk ID: a-1\nRetrieval rank: 1\nContent:\nText for a.")
    assert "\n\n[Source 2]\n" in first.format_context()
    assert "[Source 3]" not in first.format_context()


def test_missing_metadata_document_level_and_api_alias():
    context = build_context("query", [{"file_name": "local.txt", "text": "Local document"}])
    item = context.chunks[0]
    assert item.document_name == "local.txt"
    assert item.chunk_id is None and item.url is None and item.reranker_score is None
    assert "Title: local.txt" in context.format_context()
    assert "Unavailable (document-level result)" in context.format_context()


def test_source_url_fallback_domain_and_empty_text():
    context = build_context("query", [{"text": "  "}, hit(url=None, domain=None,
        source_url="https://developer.mozilla.org/en-US/docs/Web")])
    assert context.chunks[0].domain == "developer.mozilla.org"
    assert context.chunks[0].rank == 2
    assert context.chunks[0].url == "https://developer.mozilla.org/en-US/docs/Web"


@pytest.mark.parametrize("top_k", [0, -1, True, 1.5])
def test_invalid_top_k(top_k):
    with pytest.raises(ValueError, match="top_k"):
        build_context("query", [], top_k=top_k)


@pytest.mark.parametrize("query", ["", " ", None])
def test_invalid_query(query):
    with pytest.raises(ValueError, match="query"):
        build_context(query, [])


def test_malformed_evidence_fails_explicitly():
    with pytest.raises(ValueError, match="document name"):
        build_context("query", [{"text": "Unattributed content"}])
    with pytest.raises(ValueError, match="finite"):
        build_context("query", [hit(reranker_score=float("nan"))])


def test_accepts_actual_reranker_output_without_changing_it():
    from unittest.mock import Mock
    from server.reranking import rerank
    results = rerank("query", [hit("a"), hit("b")], model=Mock(
        predict=Mock(return_value=[0.1, 0.9])))
    context = build_context("query", results)
    assert [c.document_name for c in context.chunks] == ["b", "a"]
    assert context.chunks[0].reranker_score == results[0]["reranker_score"]
