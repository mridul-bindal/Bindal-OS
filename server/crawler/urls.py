"""Conservative URL identities shared by discovery and fetching."""
import re
from urllib.parse import urljoin, urlsplit, urlunsplit

from .fetch import validate_url

_UNRESERVED = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")
_ASSETS = re.compile(r"\.(?:pdf|zip|png|jpe?g|gif|svg|webp|ico|css|js|mp[34]|woff2?|ttf|exe)$", re.I)


def normalize_url(url: str, base: str | None = None) -> str:
    if not isinstance(url, str):
        raise ValueError("URL must be a string")
    value = validate_url(urljoin(base, url.strip()) if base else url.strip())
    parts = urlsplit(value)
    def percent(match):
        char = chr(int(match[1], 16))
        return char if char in _UNRESERVED else match[0].upper()
    # Preserve slash distinctions and query order: both can change server semantics.
    return validate_url(urlunsplit((parts.scheme, parts.netloc, re.sub(r"%([0-9a-fA-F]{2})", percent, parts.path or "/"),
                                    re.sub(r"%([0-9a-fA-F]{2})", percent, parts.query), "")))


def domain_of(url: str) -> str:
    return urlsplit(url).hostname or ""


def allowed_url(url: str, domains) -> bool:
    parts = urlsplit(url)
    return parts.hostname in domains and parts.port in (None, 80 if parts.scheme == "http" else 443)


def is_page(url: str) -> bool:
    return not _ASSETS.search(urlsplit(url).path)
