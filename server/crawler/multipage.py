"""Controlled crawl orchestration, reusing the single-page and indexing pipelines.

Run: python -m server.crawler.multipage --config server/crawler/crawl_config.json --dry-run
"""
import argparse
from collections import Counter
from dataclasses import asdict
import json
import time
from pathlib import Path

import httpx

from .budget import estimate_vector_budget
from .quality import QualityRejected, require_quality
from .config import CrawlConfig
from .crawl import crawl_url
from .dedup import ContentHashRecord, write_json_atomic
from .discovery import discover_sitemaps, extract_links
from .fetch import fetch_html
from .frontier import Frontier
from .policy import PolicyClient, PolicySkipped, RequestBudgetExceeded
from .storage import DEFAULT_OUTPUT_DIR, url_filename
from .urls import allowed_url, domain_of, is_page, normalize_url


class MultiPageCrawler:
    """One writer per frontier/output/index. HTTP and index dependencies are injectable."""
    def __init__(self, config, *, run_dir, output_dir=DEFAULT_OUTPUT_DIR,
                 http_client=None, index_documents=None, corpus_stats=None, progress=print):
        self.config = config
        self.run_dir, self.output_dir = Path(run_dir), Path(output_dir)
        self.frontier = Frontier(self.run_dir / "frontier.sqlite3")
        self.owns_http = http_client is None
        self.http = http_client or httpx.Client()
        self.policy = PolicyClient(self.http, config)
        self.hash_record = ContentHashRecord(self.output_dir, cache=True)
        self.index_documents = index_documents
        self.corpus_stats = corpus_stats
        self.policy.before_request = self.reserve_request
        self.progress = progress
        self.errors = []
        self.completed_urls = {}
        self.known_urls = {row[0] for row in self.frontier.db.execute("SELECT normalized_url FROM urls")}
        self.domain_counts = Counter(dict(self.frontier.db.execute("SELECT domain,COUNT(*) FROM urls GROUP BY domain")))

    def enqueue(self, raw, *, base=None, depth=0, discovery_source="seed"):
        try:
            url = normalize_url(raw, base)
        except (ValueError, TypeError):
            self.frontier.count_event("rejected_invalid")
            return False
        domain = domain_of(url)
        reason = None
        if not allowed_url(url, self.config.allowed_domains):
            # Count external links, but don't let an external site fill the frontier.
            self.frontier.count_event("rejected_domain")
            return False
        if url in self.known_urls:
            return self.frontier.add(raw, url, domain, depth, discovery_source,
                                     reason="depth" if depth > self.config.max_depth else None)
        if self.domain_counts[domain] >= self.config.max_frontier_per_domain:
            self.frontier.count_event("rejected_frontier_limit")
            return False
        if depth > self.config.max_depth:
            reason = "depth"
        elif not is_page(url):
            reason = "non_page"
        else:
            try:
                self.policy.check(url)
            except PolicySkipped as exc:
                reason = exc.reason
        self.known_urls.add(url)
        self.domain_counts[domain] += 1
        added = self.frontier.add(raw, url, domain, depth, discovery_source, reason=reason)
        if reason is None and url in self.completed_urls:
            path = self.output_dir / url_filename(url)
            self.frontier.update(url, "crawled", indexed=1, accepted=1,
                                 chunk_count=self.completed_urls[url], document_path=str(path.resolve()) if path.exists() else None)
        return added

    def error(self, url, exc):
        item = {"url": url, "error_type": type(exc).__name__, "error_message": str(exc)}
        self.errors.append(item)
        self.frontier.count_event("discovery_failures")

    def discover_links(self, html, url, depth):
        for raw, base in extract_links(html, url, limit=self.config.max_links_per_page):
            self.enqueue(raw, base=base, depth=depth + 1, discovery_source=f"link:{url}")

    def reserve_request(self):
        row = self.frontier.db.execute("SELECT value FROM counters WHERE name='http_requests'").fetchone()
        if row and row[0] >= self.config.max_requests:
            raise RequestBudgetExceeded("Persistent HTTP request safety limit reached")
        self.frontier.count_event("http_requests")
        self.frontier.db.commit()

    def run(self, *, dry_run=False, retry_failed=False, retry_only=False):
        started = time.perf_counter()
        mode_file = self.run_dir / "mode.json"
        mode = {"dry_run": dry_run, "allowed_domains": list(self.config.allowed_domains)}
        if mode_file.exists() and json.loads(mode_file.read_text()) != mode:
            raise ValueError("Use separate run directories for dry/live runs and different domain scopes")
        write_json_atomic(mode_file, mode)
        before = self.frontier.stats()
        corpus = self.corpus_stats() if self.corpus_stats else {}
        known_indexed = corpus.get("indexed_urls", {})
        self.completed_urls = known_indexed
        # Recover a crash after the manifest was committed but before frontier acknowledgement.
        for url, count in known_indexed.items():
            if url in self.known_urls:
                self.frontier.update(url, "crawled", indexed=1, accepted=1, chunk_count=count)
        self.success = Counter(corpus.get("documents_by_domain", self.frontier.stats()["indexed_by_domain"]))
        self.corpus_chunks = corpus.get("chunks", self.frontier.stats()["totals"]["chunks"])
        self.actual_points = corpus.get("actual_qdrant_points")
        initial_points = self.actual_points
        self.new_documents = 0
        self.new_chunks = 0
        self.vectors_written = 0
        self.vectors_added = 0
        self.vector_receipts_known = True
        self.index_elapsed = 0.0
        self.budget = estimate_vector_budget(target_documents=self.config.target_documents,
            indexed_documents=sum(self.success.values()), existing_chunks=self.corpus_chunks,
            estimated_chunks_per_document=self.config.estimated_chunks_per_document,
            max_vectors_estimate=self.config.max_vectors_estimate, actual_points=self.actual_points)
        self.progress(json.dumps({"vector_budget": self.budget}))
        initial_budget = dict(self.budget)
        stop = None if self.budget["allowed"] else "vector_budget_exceeded"
        if not dry_run and sum(self.success.values()) >= self.config.target_documents:
            stop = "target_reached"
        if retry_failed or retry_only:
            self.frontier.retry_failed()
        sitemap_stats = {}
        if stop is None and not retry_only:
            try:
                for seed in self.config.seeds:
                    self.enqueue(seed)
                sitemap_stats = discover_sitemaps(self.policy, self.config, self.enqueue, self.error)
            except RequestBudgetExceeded:
                stop = "request_limit"
        self.frontier.db.commit()
        batch = []
        attempts = Counter(dict(self.frontier.db.execute("SELECT domain,SUM(attempts) FROM urls GROUP BY domain")))
        sampled = Counter()
        while stop is None:
            if not self.budget["allowed"]:
                stop = "vector_budget_exceeded"
                break
            pending = Counter(domain_of(url) for url, _ in batch)
            reserved = sum(self.success.values()) + len(batch)
            if not dry_run and (reserved >= self.config.target_documents or self.new_documents + len(batch) >= self.config.batch_documents):
                self.flush(batch)
                if sum(self.success.values()) >= self.config.target_documents:
                    stop = "target_reached"
                elif self.new_documents >= self.config.batch_documents:
                    stop = "batch_complete"
                continue
            made_progress = False
            for domain in self.config.allowed_domains:
                if dry_run and sampled[domain] >= self.config.discovery_pages_per_domain:
                    continue
                if not dry_run:
                    pending = Counter(domain_of(url) for url, _ in batch)
                    if self.success[domain] + pending[domain] >= self.config.max_documents_per_domain:
                        continue
                    if sum(self.success.values()) + len(batch) >= self.config.target_documents or self.new_documents + len(batch) >= self.config.batch_documents:
                        break
                row = self.frontier.next(domain, self.config.max_depth, retry_only=retry_only)
                if row is None:
                    continue
                saved_path = Path(row["document_path"]) if row["document_path"] else self.output_dir / url_filename(row["normalized_url"])
                needs_fetch = dry_run or not (row["attempts"] and saved_path.is_file())
                if not dry_run and needs_fetch and (sum(attempts.values()) >= self.config.max_attempts_total or attempts[domain] >= self.config.max_attempts_per_domain):
                    continue
                made_progress = True
                url = row["normalized_url"]
                attempts[domain] += int(needs_fetch)
                if dry_run:
                    sampled[domain] += 1
                self.policy.last_response = None
                self.frontier.update(url, "crawling", attempts=row["attempts"] + int(needs_fetch),
                                     error_type=None, error_message=None)
                crawl_started = time.perf_counter()
                indexing_before = self.index_elapsed
                try:
                    if dry_run:
                        html = fetch_html(url, client=self.policy, timeout=self.config.timeout)
                        self.discover_links(html, str(self.policy.last_response.url), row["depth"])
                        self.frontier.update(url, "discovered", fetched=1)
                        continue
                    saved = Path(row["document_path"]) if row["document_path"] else (
                        self.output_dir / url_filename(url) if row["attempts"] else None)
                    if saved and saved.is_file():
                        document = json.loads(saved.read_text(encoding="utf-8"))
                        require_quality(document, self.config.quality)
                    else:
                        document = crawl_url(url, client=self.policy, output_dir=self.output_dir,
                            timeout=self.config.timeout, source=self.config.sources.get(domain, domain),
                            domain=domain, hash_record=self.hash_record,
                            quality_check=lambda doc: require_quality(doc, self.config.quality))
                        self.frontier.update(url, "crawling", fetched=1, extracted=1)
                        response = self.policy.last_response
                        self.discover_links(response.text, str(response.url), row["depth"])
                        if document["is_duplicate"]:
                            self.frontier.count_event("duplicate_content")
                            self.frontier.update(url, "skipped", error_type="duplicate_content")
                            continue
                        saved = self.output_dir / url_filename(url)
                    self.frontier.update(url, "crawling", document_path=str(saved.resolve()), extracted=1, accepted=1)
                    batch.append((url, document))
                    if len(batch) >= self.config.index_batch_size:
                        self.flush(batch)
                except QualityRejected as exc:
                    self.frontier.count_event("quality_filtered")
                    self.frontier.update(url, "rejected", fetched=1, extracted=int(exc.decision.reason != "empty_content"),
                        error_type=exc.decision.reason, error_message=json.dumps(exc.decision.metrics))
                    response = self.policy.last_response
                    if response is not None:
                        try:
                            self.discover_links(response.text, str(response.url), row["depth"])
                        except RequestBudgetExceeded:
                            stop = "request_limit"
                except RequestBudgetExceeded:
                    self.frontier.update(url, "queued", error_type="request_limit")
                    stop = "request_limit"
                    break
                except Exception as exc:
                    status = "skipped" if isinstance(exc, PolicySkipped) else "failed"
                    if status == "failed":
                        self.frontier.count_event("failed_requests")
                    response = self.policy.last_response
                    self.frontier.update(url, status, fetched=int(response is not None and response.is_success) or row["fetched"],
                                         error_type=getattr(exc, "reason", type(exc).__name__), error_message=str(exc))
                finally:
                    elapsed = max(0, time.perf_counter() - crawl_started - (self.index_elapsed - indexing_before))
                    self.frontier.db.execute("UPDATE urls SET crawl_seconds=crawl_seconds+? WHERE normalized_url=?", (elapsed, url))
                    self.frontier.db.commit()
                self.progress(json.dumps({"indexed": dict(self.success), "target": self.config.target_documents,
                                          "new_in_batch": self.new_documents, **self.frontier.stats()}))
            if not made_progress and stop is None:
                if batch:
                    self.flush(batch)
                    continue
                stop = "discovery_sample_complete" if dry_run else (
                    "attempt_limit" if sum(attempts.values()) >= self.config.max_attempts_total else "frontier_or_domain_limits_exhausted")
        self.flush(batch)
        if self.corpus_stats:
            current_corpus = self.corpus_stats()
            self.actual_points = current_corpus.get("actual_qdrant_points")
            self.budget = estimate_vector_budget(target_documents=self.config.target_documents,
                indexed_documents=sum(self.success.values()), existing_chunks=self.corpus_chunks,
                estimated_chunks_per_document=self.config.estimated_chunks_per_document,
                max_vectors_estimate=self.config.max_vectors_estimate, actual_points=self.actual_points)
        stats = self.frontier.stats()
        eligible = dict(self.frontier.db.execute("SELECT domain,SUM(eligible) FROM urls GROUP BY domain"))
        selected = dict.fromkeys(self.config.allowed_domains, 0)
        total_cap = self.config.max_pages_total or self.config.target_documents
        domain_cap = self.config.max_pages_per_domain or self.config.max_documents_per_domain
        while sum(selected.values()) < total_cap:
            changed = False
            for domain in selected:
                if selected[domain] < min(eligible.get(domain, 0), domain_cap) and sum(selected.values()) < total_cap:
                    selected[domain] += 1
                    changed = True
            if not changed:
                break
        events = stats["events"]
        totals = stats["totals"]
        totals.update(duplicate_urls=events.get("duplicate_urls", 0), duplicate_content=events.get("duplicate_content", 0),
                      failed_requests=events.get("failed_requests", 0), quality_filtered_pages=totals["rejected_pages"])
        batch_report = {"documents_indexed": self.new_documents, "chunks_created": self.new_chunks,
                       "page_attempts": totals["page_attempts"] - before["totals"]["page_attempts"],
                       "fetched_urls": totals["fetched_urls"] - before["totals"]["fetched_urls"],
                       "actual_qdrant_points": self.actual_points,
                       "vectors_written": self.vectors_written,
                       "vectors_added": self.actual_points - initial_points if self.actual_points is not None and initial_points is not None else (self.vectors_added if self.vector_receipts_known else None),
                       "failures": events.get("failed_requests", 0) - before["events"].get("failed_requests", 0),
                       "index_failures": events.get("index_failures", 0) - before["events"].get("index_failures", 0),
                       "duplicates": events.get("duplicate_content", 0) - before["events"].get("duplicate_content", 0),
                       "rejected_pages": totals["rejected_pages"] - before["totals"]["rejected_pages"],
                       "elapsed_seconds": time.perf_counter() - started,
                       "average_chunks_per_document": self.new_chunks / self.new_documents if self.new_documents else None}
        report = {"config": asdict(self.config), "dry_run": dry_run, **stats,
                  "quality_rejections_by_reason": dict(self.frontier.db.execute("SELECT error_type,COUNT(*) FROM urls WHERE status='rejected' GROUP BY error_type")),
                  "initial_vector_budget": initial_budget,
                  "corpus": {"target_documents": self.config.target_documents, "successfully_indexed": sum(self.success.values()),
                            "documents_by_domain": dict(self.success), "chunks": self.corpus_chunks,
                            "average_chunks_per_document": self.corpus_chunks / sum(self.success.values()) if sum(self.success.values()) else None,
                            "legacy_documents_excluded_from_target": corpus.get("legacy_documents_excluded_from_target", 0)},
                  "batch": batch_report, "vector_budget": self.budget, "actual_qdrant_points": self.actual_points,
                  "point_count_error": corpus.get("point_count_error"),
                  "average_crawl_seconds": totals["crawl_seconds"] / totals["page_attempts"] if totals["page_attempts"] else None,
                  "average_index_seconds": self.frontier.db.execute("SELECT AVG(index_seconds) FROM urls WHERE indexed=1 AND index_seconds>0").fetchone()[0],
                  "eligible_by_domain": eligible, "selected_by_domain": selected,
                  "attempted_by_domain": dict(attempts), "sampled_by_domain": dict(sampled),
                  "http_requests": self.policy.requests, "sitemaps": sitemap_stats,
                  "discovery_errors": self.errors,
                  "robots_errors": {origin: error for origin, (_, error) in self.policy.robots.items() if error},
                  "stop_reason": stop}
        write_json_atomic(self.run_dir / "report.json", report)
        # Keep each invocation's statistics instead of overwriting its history on resume.
        self.frontier.count_event("runs")
        number = self.frontier.db.execute("SELECT value FROM counters WHERE name='runs'").fetchone()[0]
        write_json_atomic(self.run_dir / f"batch-{number:04d}.json", report)
        self.progress(json.dumps(report, indent=2))
        return report

    def flush(self, batch):
        if not batch:
            return
        self.progress(f"Indexing {len(batch)} quality-approved documents...")
        started = time.perf_counter()
        try:
            if self.index_documents is None:
                raise RuntimeError("An indexing adapter is required for live crawling")
            receipt = self.index_documents([document for _, document in batch])
            receipt = receipt if isinstance(receipt, dict) else {}
            elapsed = time.perf_counter() - started
            counts = receipt.get("chunk_counts", {})
            for url, _ in batch:
                count = counts.get(url, 0)
                self.frontier.update(url, "crawled", indexed=1, chunk_count=count, index_seconds=elapsed / len(batch))
                self.success[domain_of(url)] += 1
                self.new_documents += 1
                self.new_chunks += count
                self.corpus_chunks += count
            self.vectors_written += receipt.get("vectors_written", sum(counts.values()))
            if receipt.get("vectors_added") is None:
                self.vector_receipts_known = False
            else:
                self.vectors_added += receipt["vectors_added"]
            self.actual_points = receipt.get("actual_qdrant_points", self.actual_points)
            self.budget = estimate_vector_budget(target_documents=self.config.target_documents,
                indexed_documents=sum(self.success.values()), existing_chunks=self.corpus_chunks,
                estimated_chunks_per_document=self.config.estimated_chunks_per_document,
                max_vectors_estimate=self.config.max_vectors_estimate, actual_points=self.actual_points)
        except Exception as exc:
            self.vector_receipts_known = False
            self.frontier.count_event("index_failures", len(batch))
            for url, _ in batch:
                self.frontier.update(url, "failed", error_type="indexing", error_message=str(exc))
        finally:
            self.index_elapsed += time.perf_counter() - started
            batch.clear()

    def close(self):
        self.frontier.close()
        if self.owns_http:
            self.http.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("crawl_config.json"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--retry-only", action="store_true", help="Retry attempted URLs only; do not discover new pages")
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    integers = ("target-documents", "max-documents-per-domain", "batch-documents", "max-attempts-total",
                "max-attempts-per-domain", "max-requests", "max-vectors-estimate", "max-pages-total",
                "max-pages-per-domain", "max-depth", "max-sitemaps-per-domain", "discovery-pages-per-domain")
    for name in integers:
        parser.add_argument("--" + name, type=int)
    parser.add_argument("--request-delay", type=float)
    parser.add_argument("--estimated-chunks-per-document", type=float)
    args = parser.parse_args()
    values = json.loads(args.config.read_text(encoding="utf-8"))
    for name in (*integers, "request-delay", "estimated-chunks-per-document"):
        key = name.replace("-", "_")
        if getattr(args, key) is not None:
            values[key] = getattr(args, key)
    config = CrawlConfig(**values)
    run_dir = args.run_dir or Path("crawler_runs") / ("quality-dry" if args.dry_run else "quality-live")
    from .index_adapter import CrawlIndexer
    indexer = CrawlIndexer(config)
    crawler = MultiPageCrawler(config, run_dir=run_dir, output_dir=args.output_dir,
                               index_documents=indexer, corpus_stats=lambda: indexer.stats(remote=not args.dry_run))
    try:
        report = crawler.run(dry_run=args.dry_run, retry_failed=args.retry_failed, retry_only=args.retry_only)
    finally:
        crawler.close()
        indexer.close()
    if report["stop_reason"] == "vector_budget_exceeded":
        raise SystemExit("Vector estimate exceeds configured budget; no crawl started")


if __name__ == "__main__":
    main()
