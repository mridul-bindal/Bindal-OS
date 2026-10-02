from datetime import datetime
import json
import re

import httpx
import pytest

from server.crawler import CrawlError, crawl_url, url_filename
from server.crawler.extract import clean_text, extract_content


def response_client(html="<main><h1>Example</h1><p>Hello world.</p></main>", status=200,
                    content_type="text/html; charset=utf-8"):
    return httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(
        status, text=html, headers={"Content-Type": content_type})))


def test_success_metadata_storage_and_client_ownership(tmp_path):
    with response_client("<title> A  title </title><main><p>Café &amp; code.</p></main>") as client:
        document = crawl_url("https://example.com/page#section", client=client, output_dir=tmp_path)
        assert not client.is_closed
    assert set(document) == {"url", "title", "text", "crawled_at", "content_hash", "is_duplicate", "blocks"}
    assert document["is_duplicate"] is False
    assert document["url"] == "https://example.com/page"
    assert document["title"] == "A title"
    assert document["text"] == "Café & code."
    assert datetime.fromisoformat(document["crawled_at"]).utcoffset().total_seconds() == 0
    saved = tmp_path / url_filename(document["url"])
    assert json.loads(saved.read_text(encoding="utf-8")) == {k: v for k, v in document.items() if k != "is_duplicate"}
    with response_client() as client:
        crawl_url(document["url"], client=client, output_dir=tmp_path)
    assert len(list(tmp_path.iterdir())) == 2  # Document plus persistent hash record.


def test_extraction_removes_clutter_and_preserves_inline_punctuation_and_code():
    title, text = extract_content('''<html><head><title>Guide</title><style>bad css</style></head>
      <body><nav>bad nav</nav><div>outside main</div><main><h1>Learn</h1>
      <script>bad script</script><noscript>bad noscript</noscript><aside>bad sidebar</aside>
      <p>Hello <strong>world</strong>! Use <code>db.find({x: 1})</code>.</p>
      <pre>if x &lt; 2:\n    print("a  b")\n\n    return x</pre>
      <p hidden>bad hidden</p><!-- bad comment --><footer>bad footer</footer>
      </main></body></html>''')
    assert title == "Guide"
    assert "bad" not in text and "outside main" not in text
    assert 'Hello world! Use db.find({x: 1}).' in text
    assert 'if x < 2:\n    print("a  b")\n    return x' in text
    assert "\n\n" not in text


def test_whitespace_cleaning_and_article_fallback():
    assert clean_text("  Alpha\t beta  \n\n \n Gamma   delta! \n") == "Alpha beta\nGamma delta!"
    assert extract_content("<article><h1>Heading</h1><p>A   B<br>C &amp; D.</p></article>") == (
        "Heading", "Heading\nA B\nC & D.")
    assert extract_content("<body><p>Plain body.</p></body>") == ("", "Plain body.")


@pytest.mark.parametrize("url", ["", "example.com", "ftp://example.com", "https://", None,
                                   "https://bad host/path", "https://example.com:99999",
                                   "https://user:password@example.com", "https://[invalid"])
def test_invalid_urls_rejected_before_request(url, tmp_path):
    def unexpected(request):
        pytest.fail("Invalid URL triggered HTTP request")
    with httpx.Client(transport=httpx.MockTransport(unexpected)) as client:
        with pytest.raises(ValueError, match="absolute"):
            crawl_url(url, client=client, output_dir=tmp_path)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("status", [301, 400, 403, 404, 429, 500])
def test_http_failure_does_not_save(status, tmp_path):
    with response_client(status=status) as client:
        with pytest.raises(CrawlError, match=f"HTTP {status}"):
            crawl_url("https://example.com", client=client, output_dir=tmp_path)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("exception,message", [(httpx.ReadTimeout, "timed out"),
                                               (httpx.ConnectTimeout, "timed out"),
                                               (httpx.ConnectError, "request failed")])
def test_transport_errors(exception, message, tmp_path):
    def fail(request):
        raise exception("mock failure", request=request)
    with httpx.Client(transport=httpx.MockTransport(fail)) as client:
        with pytest.raises(CrawlError, match=message):
            crawl_url("https://example.com", client=client, output_dir=tmp_path)
    assert not list(tmp_path.iterdir())


def test_redirects_and_timeout_are_passed_to_client():
    visited = []
    def handler(request):
        visited.append(str(request.url))
        assert request.extensions["timeout"]["read"] == 3
        if request.url.path == "/start":
            return httpx.Response(302, headers={"Location": "/end"})
        return httpx.Response(200, text="<p>Done</p>", headers={"Content-Type": "text/html"})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        document = crawl_url("https://example.com/start", client=client, timeout=3, output_dir=None)
    assert visited == ["https://example.com/start", "https://example.com/end"]
    assert document["url"] == visited[0]
    assert document["text"] == "Done"


@pytest.mark.parametrize("content_type,html", [("application/pdf", "binary"),
                                              ("text/html", "<script>only script</script>")])
def test_unsupported_or_empty_content(content_type, html, tmp_path):
    with response_client(html, content_type=content_type) as client:
        with pytest.raises(CrawlError):
            crawl_url("https://example.com", client=client, output_dir=tmp_path)
    assert not list(tmp_path.iterdir())


def test_stable_collision_resistant_filename():
    filename = url_filename("https://example.com/page?a=1")
    assert re.fullmatch(r"[0-9a-f]{64}\.json", filename)
    assert filename == url_filename("https://example.com/page?a=1#section")
    assert filename != url_filename("https://example.com/page?a=2")


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan")])
def test_invalid_timeout(timeout):
    with response_client() as client:
        with pytest.raises(ValueError, match="timeout"):
            crawl_url("https://example.com", client=client, timeout=timeout, output_dir=None)
