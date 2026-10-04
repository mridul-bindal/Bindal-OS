"""Bounded sitemap and HTML-link discovery into a shared frontier."""
from collections import deque
import gzip
import io
from xml.etree import ElementTree

from bs4 import BeautifulSoup

from .fetch import CrawlError
from .policy import RequestBudgetExceeded
from .urls import normalize_url


def extract_links(html, base_url, *, limit=2000):
    soup = BeautifulSoup(html, "html.parser")
    base = soup.find("base", href=True)
    if base:
        try:
            base_url = normalize_url(base["href"], base_url)
        except ValueError:
            pass
    for anchor in soup.find_all("a", href=True, limit=limit):
        yield anchor["href"], base_url


def parse_sitemap(data: bytes, *, max_bytes=20_000_000):
    if data.startswith(b"\x1f\x8b"):
        with gzip.GzipFile(fileobj=io.BytesIO(data)) as stream:
            data = stream.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise CrawlError("Sitemap exceeds max_response_bytes")
    if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        raise CrawlError("Sitemap DTD/entities are not supported")
    root = ElementTree.fromstring(data)
    kind = root.tag.rsplit("}", 1)[-1]
    if kind not in {"sitemapindex", "urlset"}:
        raise CrawlError("Not a sitemap")
    entry = "sitemap" if kind == "sitemapindex" else "url"
    urls = []
    for child in root:
        if child.tag.rsplit("}", 1)[-1] == entry:
            for node in child:
                if node.tag.rsplit("}", 1)[-1] == "loc" and node.text:
                    urls.append(node.text.strip())
                    break
    return kind, urls


def discover_sitemaps(policy, config, enqueue, report_error):
    """Round-robin sitemap fetches keep discovery balanced and bounded."""
    queues, seen = {}, set()
    for domain in config.allowed_domains:
        origin = f"https://{domain}"
        try:
            robots = policy.robots_for(origin)
            queues[domain] = deque([*robots.sitemaps, origin + "/sitemap.xml"])
        except RequestBudgetExceeded:
            raise
        except CrawlError as exc:
            report_error(origin + "/robots.txt", exc)
            queues[domain] = deque()
    counts = dict.fromkeys(config.allowed_domains, 0)
    while any(queues[d] and counts[d] < config.max_sitemaps_per_domain for d in queues):
        for domain, queue in queues.items():
            if not queue or counts[domain] >= config.max_sitemaps_per_domain:
                continue
            raw = queue.popleft()
            try:
                url = normalize_url(raw)
                if url in seen:
                    continue
                seen.add(url)
                counts[domain] += 1
                response = policy.get(url)
                response.raise_for_status()
                kind, locations = parse_sitemap(response.content, max_bytes=config.max_response_bytes)
                for location in locations:
                    if kind == "sitemapindex":
                        queue.append(normalize_url(location, str(response.url)))
                    else:
                        enqueue(location, base=str(response.url), depth=0, discovery_source=f"sitemap:{url}")
            except RequestBudgetExceeded:
                raise
            except Exception as exc:
                report_error(raw, exc)
    return {"fetched_or_rejected": counts, "pending": {d: len(q) for d, q in queues.items()}}
