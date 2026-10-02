"""HTTP fetching and URL validation."""
import math
from urllib.parse import urlsplit

import httpx


class CrawlError(Exception):
    """A page could not be fetched or contained no usable HTML text."""


def validate_url(url: str) -> str:
    """Accept absolute HTTP(S) URLs; discard fragments but preserve queries."""
    try:
        if not isinstance(url, str) or not url or any(c.isspace() or ord(c) < 32 for c in url):
            raise ValueError()
        parsed = urlsplit(url)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
            raise ValueError()
        if parsed.username is not None or parsed.password is not None or "\\" in url:
            raise ValueError()
        if parsed.port is not None and not 1 <= parsed.port <= 65535:
            raise ValueError()
        normalized = httpx.URL(url)
        return str(normalized.copy_with(fragment=None))
    except (ValueError, httpx.InvalidURL) as exc:
        raise ValueError("Expected an absolute http:// or https:// URL without credentials") from exc


def fetch_html(url: str, *, client: httpx.Client, timeout: float = 20.0) -> str:
    url = validate_url(url)
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be finite and positive")
    try:
        response = client.get(url, timeout=timeout, follow_redirects=True,
                              headers={"User-Agent": "Bindal-OS-Crawler/0.1", "Accept": "text/html,application/xhtml+xml"})
        response.raise_for_status()
    except httpx.TimeoutException as exc:
        raise CrawlError("Webpage request timed out") from exc
    except httpx.HTTPStatusError as exc:
        raise CrawlError(f"Webpage returned HTTP {exc.response.status_code}") from exc
    except (httpx.RequestError, httpx.InvalidURL) as exc:
        raise CrawlError("Webpage request failed") from exc
    content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type not in {"text/html", "application/xhtml+xml"}:
        raise CrawlError(f"Expected HTML content, received {content_type or 'no Content-Type'}")
    return response.text
