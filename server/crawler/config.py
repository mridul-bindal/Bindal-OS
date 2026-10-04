"""Limits for a sequential, explicitly scoped crawl."""
from dataclasses import dataclass, field
import math
from .quality import QualityConfig


@dataclass
class CrawlConfig:
    allowed_domains: tuple[str, ...] = ("developer.mozilla.org", "www.geeksforgeeks.org")
    sources: dict[str, str] = field(default_factory=lambda: {
        "developer.mozilla.org": "mdn", "www.geeksforgeeks.org": "gfg"})
    seeds: tuple[str, ...] = (
        "https://developer.mozilla.org/en-US/docs/Web/JavaScript",
        "https://www.geeksforgeeks.org/mongodb/mongodb-replication-and-sharding/",
    )
    target_documents: int = 5000
    max_documents_per_domain: int = 2500
    batch_documents: int = 50
    max_attempts_total: int = 20000
    max_attempts_per_domain: int = 10000
    max_requests: int = 50000
    max_vectors_estimate: int = 150000
    estimated_chunks_per_document: float = 25.0
    quality: QualityConfig = field(default_factory=QualityConfig)
    # Deprecated aliases retain their original attempt-cap semantics.
    max_pages_total: int | None = None
    max_pages_per_domain: int | None = None
    max_depth: int = 3
    request_delay: float = 2.0
    timeout: float = 20.0
    respect_robots_txt: bool = True
    user_agent: str = "Bindal-OS-Crawler/0.1"
    max_sitemaps_per_domain: int = 30
    max_frontier_per_domain: int = 60000
    max_links_per_page: int = 2000
    max_response_bytes: int = 20_000_000
    discovery_pages_per_domain: int = 2
    index_batch_size: int = 25

    def __post_init__(self):
        if isinstance(self.quality, dict):
            self.quality = QualityConfig(**self.quality)
        if not isinstance(self.quality, QualityConfig):
            raise ValueError("quality must be a QualityConfig or object")
        for old, new in (("max_pages_total", "max_attempts_total"), ("max_pages_per_domain", "max_attempts_per_domain")):
            if getattr(self, old) is not None:
                setattr(self, new, getattr(self, old))
        self.allowed_domains = tuple(dict.fromkeys(d.lower() for d in self.allowed_domains))
        if not self.allowed_domains or any(not d or any(c in d for c in "/:@ ") for d in self.allowed_domains):
            raise ValueError("allowed_domains must contain exact hostnames")
        for name in ("target_documents", "max_documents_per_domain", "batch_documents", "max_attempts_total",
                     "max_attempts_per_domain", "max_requests", "max_vectors_estimate", "max_sitemaps_per_domain",
                     "max_frontier_per_domain", "max_links_per_page", "max_response_bytes", "index_batch_size"):
            if type(getattr(self, name)) is not int or getattr(self, name) <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if not math.isfinite(self.estimated_chunks_per_document) or self.estimated_chunks_per_document <= 0:
            raise ValueError("estimated_chunks_per_document must be positive and finite")
        for name in ("max_depth", "discovery_pages_per_domain"):
            if type(getattr(self, name)) is not int or getattr(self, name) < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if not math.isfinite(self.request_delay) or self.request_delay < 0:
            raise ValueError("request_delay must be finite and non-negative")
        if not math.isfinite(self.timeout) or self.timeout <= 0:
            raise ValueError("timeout must be positive and finite")
        if self.respect_robots_txt is not True:
            raise ValueError("robots.txt cannot be disabled")
        if not self.user_agent.strip() or any(c in self.user_agent for c in "\r\n"):
            raise ValueError("Invalid user agent")
