from contextlib import closing
import gzip
import json
from unittest.mock import Mock

import httpx
import pytest
from qdrant_client import QdrantClient

from server.crawler.config import CrawlConfig
from server.crawler.discovery import extract_links, parse_sitemap
from server.crawler.fetch import CrawlError
from server.crawler.frontier import Frontier
from server.crawler.multipage import MultiPageCrawler
from server.crawler.policy import PolicyClient, PolicySkipped
from server.crawler.urls import allowed_url, normalize_url


def config(**kwargs):
    return CrawlConfig(**{**dict(allowed_domains=("a.test", "b.test"),
        sources={"a.test": "mdn", "b.test": "gfg"}, seeds=("https://a.test/start", "https://b.test/start"),
        request_delay=0, max_pages_total=4, max_pages_per_domain=2, max_sitemaps_per_domain=3,
        discovery_pages_per_domain=1, index_batch_size=2, quality={"enabled": False}), **kwargs})


@pytest.mark.parametrize("raw,base,expected", [
    ("HTTPS://A.TEST:443", None, "https://a.test/"),
    ("../guide#section", "https://a.test/docs/start", "https://a.test/guide"),
    ("https://a.test/%7euser?q=%41%2f", None, "https://a.test/~user?q=A%2F"),
    ("//b.test/docs", "https://a.test/", "https://b.test/docs"),
    ("https://a.test/a/%2e%2e/b", None, "https://a.test/b"),
])
def test_normalization(raw, base, expected):
    assert normalize_url(raw, base) == expected


def test_normalization_preserves_meaning_and_exact_domains():
    assert normalize_url("https://a.test/a") != normalize_url("https://a.test/a/")
    assert normalize_url("https://a.test/?a=1&b=2") != normalize_url("https://a.test/?b=2&a=1")
    assert allowed_url("https://a.test/a", ["a.test"])
    assert not allowed_url("https://sub.a.test/a", ["a.test"])
    assert not allowed_url("https://a.test:123/a", ["a.test"])
    for value in ["javascript:alert(1)", "ftp://a.test", "https://user:pass@a.test"]:
        with pytest.raises(ValueError):
            normalize_url(value)


@pytest.mark.parametrize("kwargs", [{"respect_robots_txt": False}, {"max_pages_total": 0},
    {"request_delay": -1}, {"max_depth": -1}, {"timeout": float("nan")}])
def test_invalid_config(kwargs):
    with pytest.raises(ValueError):
        config(**kwargs)


def test_frontier_persists_deduplicates_and_recovers(tmp_path):
    path = tmp_path / "frontier.db"
    with closing(Frontier(path)) as frontier:
        assert frontier.add("raw", "https://a.test/a", "a.test", 2, "link:parent")
        assert not frontier.add("raw#x", "https://a.test/a", "a.test", 1, "sitemap:a")
        row = frontier.next("a.test", 1)
        assert row["depth"] == 1
        frontier.update(row["normalized_url"], "crawling", attempts=1)
    with closing(Frontier(path)) as frontier:
        assert frontier.next("a.test", 2)["attempts"] == 1
        assert frontier.stats()["events"]["duplicate_urls"] == 1
        frontier.update("https://a.test/a", "failed", error_type="Timeout", error_message="timeout")
        assert frontier.next("a.test", 2) is None
        frontier.retry_failed()
        assert frontier.next("a.test", 2)


def test_sitemap_formats_and_bounded_gzip():
    xml = b'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://a.test/a</loc></url></urlset>'
    assert parse_sitemap(xml) == ("urlset", ["https://a.test/a"])
    assert parse_sitemap(gzip.compress(xml)) == parse_sitemap(xml)
    assert parse_sitemap(b"<sitemapindex><sitemap><loc>https://a.test/child.xml</loc></sitemap></sitemapindex>")[0] == "sitemapindex"
    with pytest.raises(CrawlError):
        parse_sitemap(gzip.compress(xml), max_bytes=10)
    with pytest.raises(CrawlError):
        parse_sitemap(b'<!DOCTYPE xml><urlset/>')


def test_link_extraction_resolves_base():
    links = list(extract_links('<base href="/docs/"><a href="guide#top">Read</a><a>None</a>', "https://a.test/a"))
    assert [normalize_url(raw, base) for raw, base in links] == ["https://a.test/docs/guide"]


def fake_site(request):
    url = str(request.url)
    origin = f"https://{request.url.host}"
    path = request.url.path
    if path == "/robots.txt":
        return httpx.Response(200, text=f"User-agent: *\nDisallow: /private\nSitemap: {origin}/map.xml")
    if path == "/map.xml":
        return httpx.Response(200, text=f"<sitemapindex><sitemap><loc>{origin}/nested.xml.gz</loc></sitemap></sitemapindex>")
    if path == "/nested.xml.gz":
        xml = f"<urlset><url><loc>{origin}/next</loc></url><url><loc>{origin}/private</loc></url><url><loc>{origin}/start#top</loc></url><url><loc>https://external.test/no</loc></url></urlset>"
        return httpx.Response(200, content=gzip.compress(xml.encode()))
    if path == "/sitemap.xml":
        return httpx.Response(404)
    return httpx.Response(200, headers={"Content-Type": "text/html"}, text=f'<html><title>Guide</title><main><h1>{url}</h1><p>Unique tutorial {url}.</p><a href="/linked">Link</a><a href="/private">Private</a><a href="https://external.test/no">External</a></main></html>')


def make_crawler(tmp_path, settings=None, handler=fake_site, indexer=None):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return MultiPageCrawler(settings or config(), run_dir=tmp_path / "run", output_dir=tmp_path / "documents",
                            http_client=client, index_documents=indexer or Mock(), progress=lambda _: None)


def test_dry_run_nested_sitemaps_links_robots_domains_and_no_index(tmp_path):
    indexer = Mock()
    with closing(make_crawler(tmp_path, indexer=indexer)) as crawler:
        report = crawler.run(dry_run=True)
        assert report["selected_by_domain"] == {"a.test": 2, "b.test": 2}
        assert report["events"]["discovered_sitemap"] > 0
        assert report["events"]["discovered_link"] > 0
        assert report["events"]["rejected_domain"] > 0
        assert report["events"]["rejected_robots"] == 2
        assert report["events"]["duplicate_urls"] > 0
        assert report["sampled_by_domain"] == {"a.test": 1, "b.test": 1}
    indexer.assert_not_called()
    assert not (tmp_path / "documents").exists()


@pytest.mark.parametrize("total,per_domain,expected", [(3, 3, {"a.test": 2, "b.test": 1}), (10, 1, {"a.test": 1, "b.test": 1})])
def test_total_per_domain_limits_and_balance(tmp_path, total, per_domain, expected):
    with closing(make_crawler(tmp_path, config(max_pages_total=total, max_pages_per_domain=per_domain))) as crawler:
        report = crawler.run()
        assert report["indexed_by_domain"] == expected
        assert report["attempted_by_domain"] == expected
    with closing(make_crawler(tmp_path, config(max_pages_total=total, max_pages_per_domain=per_domain))) as resumed:
        assert resumed.run()["indexed_by_domain"] == expected


def test_depth_limits_and_content_dedup(tmp_path):
    def site(request):
        if request.url.path in ("/start", "/next"):
            return httpx.Response(200, headers={"Content-Type": "text/html"}, text='<main>Same content<a href="/deep">Deep</a></main>')
        return fake_site(request)
    with closing(make_crawler(tmp_path, config(max_depth=0, max_pages_total=10), handler=site)) as crawler:
        report = crawler.run()
        assert sum(report["indexed_by_domain"].values()) == 1
        assert report["events"]["duplicate_content"] == 3
        assert report["events"]["rejected_depth"] == 2
        assert crawler.frontier.next("a.test", 0) is None


def test_page_failure_does_not_stop_other_pages(tmp_path):
    def site(request):
        if request.url.host == "a.test" and request.url.path == "/start":
            raise httpx.ReadTimeout("timed out", request=request)
        return fake_site(request)
    with closing(make_crawler(tmp_path, handler=site)) as crawler:
        report = crawler.run()
        assert report["domains"]["a.test"]["failed"] == 1
        assert sum(report["indexed_by_domain"].values()) == 3


def test_saved_documents_retry_indexing_without_refetch_or_dedup_loss(tmp_path):
    indexer = Mock(side_effect=RuntimeError("index unavailable"))
    with closing(make_crawler(tmp_path, indexer=indexer)) as crawler:
        report = crawler.run()
        assert sum(v.get("failed", 0) for v in report["domains"].values()) == 4
    requests = []
    def site(request):
        requests.append(request.url.path)
        return fake_site(request)
    recovered = Mock()
    with closing(make_crawler(tmp_path, handler=site, indexer=recovered)) as crawler:
        report = crawler.run(retry_failed=True)
        assert sum(report["indexed_by_domain"].values()) == 4
    assert "/start" not in requests and "/next" not in requests


@pytest.mark.parametrize("location,reason", [("https://external.test/no", "domain"), ("/private", "robots")])
def test_redirect_targets_are_checked_before_fetch(location, reason):
    seen = []
    def site(request):
        seen.append(str(request.url))
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": location})
        return fake_site(request)
    with httpx.Client(transport=httpx.MockTransport(site)) as client:
        policy = PolicyClient(client, config())
        with pytest.raises(PolicySkipped, match=reason):
            policy.get("https://a.test/start")
    assert all("private" not in url and "external" not in url for url in seen)


def test_robots_unavailable_fails_closed_and_is_cached():
    handler = Mock(return_value=httpx.Response(503))
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        policy = PolicyClient(client, config())
        for _ in range(2):
            with pytest.raises(PolicySkipped, match="robots_unavailable"):
                policy.get("https://a.test/start")
    assert handler.call_count == 1


def test_response_size_and_redirect_loop_are_bounded():
    def site(request):
        if request.url.path == "/huge":
            return httpx.Response(200, content=b"x" * 500)
        if request.url.path == "/loop":
            return httpx.Response(302, headers={"Location": "/loop"})
        return fake_site(request)
    with httpx.Client(transport=httpx.MockTransport(site)) as client:
        policy = PolicyClient(client, config(max_response_bytes=200))
        with pytest.raises(CrawlError, match="max_response_bytes"):
            policy.get("https://a.test/huge")
        with pytest.raises(CrawlError, match="Redirect loop"):
            policy.get("https://a.test/loop")


def test_dry_and_live_frontiers_cannot_be_mixed(tmp_path):
    with closing(make_crawler(tmp_path)) as crawler:
        crawler.run(dry_run=True)
    with closing(make_crawler(tmp_path)) as crawler:
        with pytest.raises(ValueError, match="separate run directories"):
            crawler.run()


def test_frontier_limit_and_empty_frontier_stop(tmp_path):
    with closing(make_crawler(tmp_path, config(max_frontier_per_domain=1, max_pages_total=10))) as crawler:
        report = crawler.run()
        assert report["events"]["rejected_frontier_limit"] > 0
        assert sum(report["indexed_by_domain"].values()) == 2
        assert crawler.frontier.next("a.test", 3) is None


def test_robots_specific_agent_wildcard_and_crawl_delay():
    now, pauses = [0.0], []
    def sleep(seconds):
        pauses.append(seconds)
        now[0] += seconds
    def site(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /\nUser-agent: Bindal-OS-Crawler\nDisallow: /*secret*\nAllow: /secret/public$\nCrawl-delay: 3")
        return fake_site(request)
    with httpx.Client(transport=httpx.MockTransport(site)) as client:
        policy = PolicyClient(client, config(request_delay=1), sleep=sleep, clock=lambda: now[0])
        policy.get("https://a.test/start")
        policy.get("https://a.test/secret/public")
        with pytest.raises(PolicySkipped):
            policy.get("https://a.test/mysecret")
    assert pauses == [3, 3]


def test_end_to_end_metadata_and_scoped_vector_replacement(tmp_path, monkeypatch):
    from server.crawler.chunking import chunk_crawled_documents
    from server.crawler.indexing import index_crawled_chunks
    from server.hybrid_search import service
    from server.search_engine.BM25 import search_bm25_index
    model = Mock()
    model.encode.side_effect = lambda texts: [[0.1] * 384 for _ in texts]
    # Avoid Mock's auto-generated tokenizer/max_seq_length attributes.
    del model.tokenizer
    del model.max_seq_length
    manifest = tmp_path / "index.json"
    with closing(QdrantClient(":memory:")) as qdrant:
        def index(documents):
            chunks = chunk_crawled_documents(documents)
            assert all(c.source in ("mdn", "gfg") and c.domain in ("a.test", "b.test") for c in chunks)
            index_crawled_chunks(chunks, client=qdrant, collection="test", index_file=manifest, model=model)
        with closing(make_crawler(tmp_path, indexer=index)) as crawler:
            report = crawler.run()
            assert sum(report["indexed_by_domain"].values()) == 4
        result = json.loads(manifest.read_text())
        assert search_bm25_index("tutorial", result["bm25_index"])
        documents = [json.loads(p.read_text()) for p in (tmp_path / "documents").glob("*.json") if p.name != "content_hashes.json"]
        assert all(d["source"] and d["domain"] and d["blocks"] for d in documents)
        before = qdrant.count("test").count
        index(documents[:1])
        assert qdrant.count("test").count == before
        points = qdrant.scroll("test", limit=100)[0]
        assert {p.payload["source"] for p in points} == {"mdn", "gfg"}
        assert all(p.payload["index_scope"] == "crawler:" + p.payload["url"] for p in points)
        monkeypatch.setattr(service, "DEFAULT_INDEX_FILE", manifest)
        metadata = service.load_crawler_documents({})
        assert {d["source"] for d in metadata.values()} == {"mdn", "gfg"}
        assert all(d["domain"] for d in metadata.values())
        from server.semantic_search.search import semantic_search
        hits = semantic_search("tutorial", client=qdrant, collection="test", model=model, top_k=100)
        assert {hit.source for hit in hits} == {"mdn", "gfg"}
        assert {hit.domain for hit in hits} == {"a.test", "b.test"}


def test_source_label_migration_cleans_legacy_scope_without_deleting_other_pages():
    from server.semantic_search.embeddings import EmbeddedChunk
    from server.semantic_search.vector_store import store_chunks
    with closing(QdrantClient(":memory:")) as client:
        def chunk(name, source=None):
            return EmbeddedChunk(name, name + "::chunk-0", "text", [.1] * 384,
                                 {"source": source} if source else {})
        store_chunks(client, "test", [chunk("old")], source="crawler:https://a.test/a")
        # Simulate pre-migration points without index_scope.
        old = client.scroll("test")[0][0]
        client.delete_payload("test", keys=["index_scope"], points=[old.id])
        store_chunks(client, "test", [chunk("other", "mdn")], source="crawler:https://a.test/b")
        store_chunks(client, "test", [chunk("new", "mdn")], source="crawler:https://a.test/a")
        assert {p.payload["document_name"] for p in client.scroll("test")[0]} == {"new", "other"}
