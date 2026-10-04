"""Receipts/statistics around the existing indexer; no new indexing algorithms."""
from collections import Counter
import json

from .chunking import chunk_crawled_documents
from .indexing import DEFAULT_INDEX_FILE, index_crawled_chunks
from .quality import assess_quality
from .urls import domain_of


class CrawlIndexer:
    def __init__(self, config, *, index_file=DEFAULT_INDEX_FILE):
        self.config, self.index_file = config, index_file
        self.connection = None

    def connect(self):
        if self.connection is None:
            from server.semantic_search.vector_store import connect_qdrant
            self.connection = connect_qdrant()
        return self.connection

    def point_count(self):
        client, collection = self.connect()
        return client.count(collection, exact=True).count

    def stats(self, *, remote=True):
        manifest = json.loads(self.index_file.read_text(encoding="utf-8")) if self.index_file.exists() else {"documents": {}}
        counts, chunks, completed = Counter(), 0, {}
        all_chunks, excluded = 0, 0
        for url, document in manifest["documents"].items():
            page = document.get("chunks", [])
            all_chunks += len(page)
            domain = domain_of(url)
            first = page[0] if page else {}
            if domain not in self.config.allowed_domains:
                continue
            sample = {**document, "title": first.get("title", "")}
            if not page or not first.get("source") or first.get("domain") != domain or not assess_quality(sample, self.config.quality).accepted:
                excluded += 1
                continue
            counts[domain] += 1
            chunks += len(page)
            completed[url] = len(page)
        points, point_error = None, None
        if remote:
            try:
                points = self.point_count()
            except Exception as exc:
                point_error = type(exc).__name__
        return {"documents_by_domain": dict(counts), "chunks": chunks, "all_manifest_chunks": all_chunks,
                "indexed_urls": completed, "actual_qdrant_points": points,
                "point_count_error": point_error, "legacy_documents_excluded_from_target": excluded}

    def __call__(self, documents):
        chunks = chunk_crawled_documents(documents)
        counts = Counter(chunk.source_url for chunk in chunks)
        if len(counts) != len(documents):
            raise ValueError("Every accepted document must produce chunks")
        client, collection = self.connect()
        before = None
        try:
            before = self.point_count()
        except Exception:
            pass
        index_crawled_chunks(chunks, client=client, collection=collection, index_file=self.index_file)
        after = None
        try:
            after = self.point_count()
        except Exception:
            pass
        return {"chunk_counts": dict(counts), "vectors_written": len(chunks),
                "vectors_added": after - before if after is not None and before is not None else None,
                "actual_qdrant_points": after}

    def close(self):
        if self.connection:
            self.connection[0].close()
