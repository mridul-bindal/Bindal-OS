from contextlib import closing
import json
from unittest.mock import Mock

import httpx
import pytest

from server.crawler.budget import estimate_vector_budget
from server.crawler.config import CrawlConfig
from server.crawler.multipage import MultiPageCrawler
from server.crawler.quality import QualityConfig, assess_quality


PROSE = """A database index stores a searchable representation of selected fields.
Applications can use indexes to locate matching records without scanning every document.
Choosing an appropriate compound index depends on equality predicates, ordering requirements,
range conditions, selectivity, and the workload. Developers should inspect execution plans,
measure latency, compare examined keys with returned rows, and account for write overhead.
This example explains how ordered structures improve retrieval while additional storage and
maintenance costs affect updates. Production systems benefit from observing realistic traffic
before changing configurations. Testing different data distributions helps uncover unexpected
performance problems and identify a useful balance between read speed and resource consumption."""


@pytest.mark.parametrize("document,reason", [
    ({"text": "   "}, "empty_content"),
    ({"text": "Tiny fragment"}, "too_short"),
    ({"title": "Page not found | MDN", "text": "Sorry, the page you requested does not exist."}, "soft_404"),
    ({"title": "Service unavailable", "text": "Please try again later."}, "error_page"),
    ({"text": "Accept all cookies\nPrivacy policy\nTerms of use\nAll rights reserved"}, "boilerplate"),
    ({"text": "Home\nMenu\nSearch\nNext\nPrevious\nContact us"}, "navigation_content"),
    ({"text": "database " * 100}, "insufficient_content"),
    ({"text": "A repeated welcome message for our visitors\n" * 30}, "boilerplate"),
])
def test_quality_reasons(document, reason):
    decision = assess_quality(document)
    assert not decision.accepted and decision.reason == reason
    assert "words" in decision.metrics and "unique_words" in decision.metrics


def test_quality_accepts_prose_code_and_articles_discussing_errors():
    for title in ["Database indexing", "Understanding HTTP 404 errors", "404 Not Found - HTTP | MDN"]:
        assert assess_quality({"title": title, "text": PROSE + "\nif (status == 404) { return fallback(); }"}).accepted
    # Character count alone must not reject a substantial short-word document.
    assert assess_quality({"text": PROSE}, QualityConfig(min_characters=10000)).accepted
    assert not assess_quality({"text": PROSE}, QualityConfig(min_characters=10000, min_words=200)).accepted


@pytest.mark.parametrize("settings", [{"min_words": 0}, {"max_boilerplate_ratio": 1.1}, {"min_unique_ratio": float("nan")}])
def test_quality_threshold_validation(settings):
    with pytest.raises(ValueError):
        QualityConfig(**settings)


def settings(**overrides):
    return CrawlConfig(**{**dict(allowed_domains=("a.test", "b.test"), sources={"a.test": "mdn", "b.test": "gfg"},
        seeds=("https://a.test/bad", "https://b.test/bad"), target_documents=4, max_documents_per_domain=2,
        batch_documents=50, index_batch_size=25, max_attempts_total=30, max_attempts_per_domain=20,
        max_sitemaps_per_domain=1, request_delay=0), **overrides})


def site(request):
    path = request.url.path
    origin = f"https://{request.url.host}"
    if path == "/robots.txt":
        return httpx.Response(200, text="User-agent: *\nDisallow: /private")
    if path == "/sitemap.xml":
        locations = ["bad", "one", "duplicate", "failure", "two", "three", "four", "private"]
        return httpx.Response(200, text="<urlset>" + "".join(f"<url><loc>{origin}/{p}</loc></url>" for p in locations) + "</urlset>")
    if path == "/bad":
        return httpx.Response(200, headers={"Content-Type": "text/html"}, text="<title>Page not found</title><main>Sorry, page not found.</main>")
    if path == "/failure":
        return httpx.Response(503)
    identity = "/one" if path == "/duplicate" else path
    return httpx.Response(200, headers={"Content-Type": "text/html"}, text=f"<title>Guide {identity}</title><main><h1>{origin}{identity}</h1><p>{PROSE}</p></main>")


def crawler(tmp_path, config=None, indexer=None, handler=site, corpus_stats=None):
    def index(docs):
        assert all(d["source"] and d["domain"] and d["content_hash"] for d in docs)
        return {"chunk_counts": {d["url"]: 2 for d in docs}, "vectors_written": 2 * len(docs), "vectors_added": 2 * len(docs)}
    return MultiPageCrawler(config or settings(), run_dir=tmp_path / "run", output_dir=tmp_path / "docs",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)), index_documents=indexer or index,
        corpus_stats=corpus_stats, progress=lambda _: None)


def test_successful_target_ignores_rejections_duplicates_and_failures(tmp_path):
    with closing(crawler(tmp_path)) as run:
        report = run.run()
        assert report["stop_reason"] == "target_reached"
        assert report["corpus"]["successfully_indexed"] == 4
        assert report["corpus"]["documents_by_domain"] == {"a.test": 2, "b.test": 2}
        assert report["batch"]["rejected_pages"] == 2
        assert report["batch"]["duplicates"] == 2
        assert report["batch"]["failures"] == 2
        assert report["totals"]["soft_404_pages"] == 2
        assert report["totals"]["robots_blocked_urls"] == 2
        assert report["totals"]["successfully_indexed_documents"] == 4
        assert report["totals"]["page_attempts"] == 10
        assert report["batch"]["chunks_created"] == report["batch"]["vectors_added"] == 8
        assert report["corpus"]["average_chunks_per_document"] == 2
        assert report["average_index_seconds"] >= 0
    files = [p for p in (tmp_path / "docs").glob("*.json") if p.name != "content_hashes.json"]
    assert len(files) == 4
    assert all("/bad" not in json.loads(p.read_text())["url"] for p in files)


def test_global_target_and_batch_reservations_do_not_overshoot(tmp_path):
    with closing(crawler(tmp_path, settings(target_documents=3, max_documents_per_domain=3))) as run:
        report = run.run()
        assert report["corpus"]["successfully_indexed"] == 3
        assert max(report["corpus"]["documents_by_domain"].values()) == 2


def test_attempt_safety_limit_counts_unsuccessful_fetches(tmp_path):
    with closing(crawler(tmp_path, settings(max_attempts_total=3))) as run:
        report = run.run()
        assert report["stop_reason"] == "attempt_limit"
        assert report["totals"]["page_attempts"] == 3
        assert report["corpus"]["successfully_indexed"] == 1


def test_request_budget_includes_discovery_and_persists(tmp_path):
    requests = []
    def handler(request):
        requests.append(str(request.url))
        return site(request)
    for _ in range(2):
        with closing(crawler(tmp_path, settings(max_requests=3), handler=handler)) as run:
            report = run.run()
            assert report["stop_reason"] == "request_limit"
    assert len(requests) == 3


def test_vector_estimate_uses_observed_average_and_existing_points():
    budget = estimate_vector_budget(target_documents=5000, indexed_documents=50, existing_chunks=1500,
        actual_points=1700, estimated_chunks_per_document=20, max_vectors_estimate=150000)
    assert budget["estimated_chunks_per_document"] == 30
    assert budget["estimated_vectors"] == 150200
    assert not budget["allowed"]


def test_over_budget_stops_before_any_http_or_indexing(tmp_path):
    http = Mock(side_effect=AssertionError("must not fetch"))
    index = Mock()
    with closing(crawler(tmp_path, settings(max_vectors_estimate=1), handler=http, indexer=index)) as run:
        report = run.run()
        assert report["stop_reason"] == "vector_budget_exceeded"
    http.assert_not_called()
    index.assert_not_called()


def test_batches_resume_without_resetting_successes_or_reindexing(tmp_path):
    indexed_urls = []
    def index(docs):
        indexed_urls.extend(d["url"] for d in docs)
        return {"chunk_counts": {d["url"]: 3 for d in docs}, "vectors_added": len(docs) * 3}
    config = settings(batch_documents=2)
    with closing(crawler(tmp_path, config, indexer=index)) as run:
        first = run.run()
        assert first["batch"]["documents_indexed"] == 2
        assert first["stop_reason"] == "batch_complete"
    with closing(crawler(tmp_path, config, indexer=index)) as run:
        second = run.run()
        assert second["batch"]["documents_indexed"] == 2
        assert second["corpus"]["successfully_indexed"] == 4
        assert second["corpus"]["chunks"] == 12
    with closing(crawler(tmp_path, config, indexer=index)) as run:
        assert run.run()["batch"]["documents_indexed"] == 0
    assert len(indexed_urls) == len(set(indexed_urls)) == 4
    assert len(list((tmp_path / "run").glob("batch-*.json"))) == 3


def test_existing_corpus_counts_toward_target(tmp_path):
    stats = lambda: {"documents_by_domain": {"a.test": 1, "b.test": 1}, "chunks": 10, "actual_qdrant_points": 20}
    with closing(crawler(tmp_path, corpus_stats=stats)) as run:
        report = run.run()
        assert report["batch"]["documents_indexed"] == 2
        assert report["corpus"]["successfully_indexed"] == 4
        assert report["vector_budget"]["indexed_documents"] == 4


def test_already_indexed_urls_discovered_in_new_frontier_are_not_refetched(tmp_path):
    fetched = []
    def handler(request):
        fetched.append(str(request.url))
        return site(request)
    stats = lambda: {"documents_by_domain": {"a.test": 1, "b.test": 1}, "chunks": 4,
        "indexed_urls": {"https://a.test/one": 2, "https://b.test/one": 2}}
    with closing(crawler(tmp_path, handler=handler, corpus_stats=stats)) as run:
        report = run.run()
        assert report["corpus"]["successfully_indexed"] == 4
    assert "https://a.test/one" not in fetched and "https://b.test/one" not in fetched


def test_manifest_statistics_exclude_legacy_low_quality_without_deleting_it(tmp_path):
    from server.crawler.index_adapter import CrawlIndexer
    path = tmp_path / "index.json"
    good = {"text": PROSE, "chunks": [{"title": "Indexing", "source": "mdn", "domain": "a.test"}]}
    bad = {"text": "Page not found", "chunks": [{"title": "Page not found", "source": "mdn", "domain": "a.test"}]}
    path.write_text(json.dumps({"documents": {"https://a.test/one": good, "https://a.test/missing": bad}}))
    result = CrawlIndexer(settings(), index_file=path).stats(remote=False)
    assert result["documents_by_domain"] == {"a.test": 1}
    assert result["legacy_documents_excluded_from_target"] == 1
    assert len(json.loads(path.read_text())["documents"]) == 2


def test_failed_indexing_is_not_success_and_other_pages_can_fill_target(tmp_path):
    calls = []
    def index(docs):
        calls.append(docs)
        if len(calls) == 1:
            raise RuntimeError("temporary upload failure")
        return {"chunk_counts": {d["url"]: 2 for d in docs}}
    with closing(crawler(tmp_path, settings(index_batch_size=2), indexer=index)) as run:
        report = run.run()
        assert report["batch"]["index_failures"] == 2
        assert report["corpus"]["successfully_indexed"] == 4
        assert report["totals"]["failed_urls"] == 4  # two HTTP, two indexing


def test_retry_only_recovers_saved_batch_without_fetching_new_urls(tmp_path):
    config = settings(max_attempts_total=4, index_batch_size=2)
    with closing(crawler(tmp_path, config, indexer=Mock(side_effect=RuntimeError("disconnect")))) as run:
        assert run.run()["corpus"]["successfully_indexed"] == 0
    http = Mock(side_effect=AssertionError("saved indexing recovery must not fetch"))
    with closing(crawler(tmp_path, config, handler=http)) as run:
        result = run.run(retry_only=True)
        assert result["batch"]["documents_indexed"] == 2
        assert result["batch"]["page_attempts"] == 0
        assert result["http_requests"] == 0
    http.assert_not_called()


def test_vector_additions_include_partial_uploads_from_failed_batches(tmp_path):
    points = [100]
    def stats():
        return {"documents_by_domain": {}, "chunks": 0, "actual_qdrant_points": points[0]}
    calls = [0]
    def index(docs):
        calls[0] += 1
        if calls[0] == 1:
            points[0] += 1  # a write succeeded before the connection failed
            raise RuntimeError("disconnect")
        points[0] += 2 * len(docs)
        return {"chunk_counts": {d["url"]: 2 for d in docs}, "vectors_added": 2 * len(docs)}
    with closing(crawler(tmp_path, settings(index_batch_size=2), indexer=index, corpus_stats=stats)) as run:
        result = run.run()
        assert result["batch"]["vectors_added"] == 9
        assert result["batch"]["vectors_written"] == 8
        assert result["batch"]["documents_indexed"] == 4
