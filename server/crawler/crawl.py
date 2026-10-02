"""Fetch, extract and optionally persist one URL."""
from datetime import datetime, timezone
from pathlib import Path

import httpx

from .extract import extract_structured_content
from .fetch import CrawlError, fetch_html, validate_url
from .storage import DEFAULT_OUTPUT_DIR, save_document
from .dedup import content_hash


def crawl_url(url: str, *, output_dir: Path | None = DEFAULT_OUTPUT_DIR,
              timeout: float = 20.0, client: httpx.Client | None = None) -> dict:
    """Return document metadata, typed HTML blocks, content_hash, and duplicate status.

    is_duplicate is False when saved, True when skipped, or None when
    output_dir=None (no persistence or duplicate check). Only document metadata
    is stored in JSON; the status is returned to the caller.

    The URL is the normalized requested URL (not the redirect destination).
    Injected clients remain caller-owned. No links are followed beyond HTTP
    redirects, and no retrieval or indexing components are involved.
    """
    url = validate_url(url)
    if client is None:
        with httpx.Client() as owned_client:
            html = fetch_html(url, client=owned_client, timeout=timeout)
    else:
        html = fetch_html(url, client=client, timeout=timeout)
    title, text, blocks = extract_structured_content(html)
    if not text:
        raise CrawlError("Page contains no usable text")
    document = {"url": url, "title": title, "text": text, "blocks": blocks,
                "content_hash": content_hash(text),
                "crawled_at": datetime.now(timezone.utc).isoformat()}
    document["is_duplicate"] = None
    if output_dir is not None:
        document["is_duplicate"] = save_document(document, output_dir) is None
    return document
