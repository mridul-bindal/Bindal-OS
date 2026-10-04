"""A local SQLite frontier for one sequential crawler process."""
from pathlib import Path
import sqlite3


class Frontier:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS urls (
                normalized_url TEXT PRIMARY KEY, url TEXT NOT NULL, domain TEXT NOT NULL,
                depth INTEGER NOT NULL, discovery_source TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'discovered', attempts INTEGER NOT NULL DEFAULT 0,
                error_type TEXT, error_message TEXT, document_path TEXT,
                indexed INTEGER NOT NULL DEFAULT 0);
            CREATE INDEX IF NOT EXISTS queue ON urls(domain, status, depth);
            CREATE TABLE IF NOT EXISTS counters (name TEXT PRIMARY KEY, value INTEGER NOT NULL);
        ''')
        columns = {row[1] for row in self.db.execute("PRAGMA table_info(urls)")}
        for name, declaration in {"fetched": "INTEGER DEFAULT 0", "extracted": "INTEGER DEFAULT 0",
                                  "accepted": "INTEGER DEFAULT 0", "eligible": "INTEGER DEFAULT 0",
                                  "chunk_count": "INTEGER DEFAULT 0", "crawl_seconds": "REAL DEFAULT 0",
                                  "index_seconds": "REAL DEFAULT 0"}.items():
            if name not in columns:
                self.db.execute(f"ALTER TABLE urls ADD COLUMN {name} {declaration}")
        self.db.execute("UPDATE urls SET eligible=1 WHERE status IN ('queued','crawling','crawled','discovered','failed')")
        # An interrupted fetch/save/index is safe to retry using the saved document.
        self.db.execute("UPDATE urls SET status='queued' WHERE status='crawling'")
        self.db.commit()

    def count_event(self, name, amount=1):
        self.db.execute("INSERT INTO counters VALUES (?,?) ON CONFLICT(name) DO UPDATE SET value=value+excluded.value", (name, amount))

    def add(self, url, normalized, domain, depth, discovery_source, *, reason=None):
        existing = self.db.execute("SELECT depth FROM urls WHERE normalized_url=?", (normalized,)).fetchone()
        if existing:
            self.count_event("duplicate_urls")
            if reason is None and depth < existing["depth"]:
                self.db.execute("UPDATE urls SET depth=?, status=CASE WHEN error_type='depth' THEN 'queued' ELSE status END, error_type=CASE WHEN error_type='depth' THEN NULL ELSE error_type END WHERE normalized_url=?", (depth, normalized))
            return False
        self.db.execute("INSERT INTO urls(normalized_url,url,domain,depth,discovery_source,status,error_type) VALUES (?,?,?,?,?,?,?)",
                        (normalized, url, domain, depth, discovery_source, "skipped" if reason else "queued", reason))
        if reason is None:
            self.db.execute("UPDATE urls SET eligible=1 WHERE normalized_url=?", (normalized,))
        self.count_event("discovered_" + discovery_source.split(":", 1)[0])
        if reason:
            self.count_event("rejected_" + reason)
        return reason is None

    def update(self, url, status, **fields):
        allowed = {"attempts", "error_type", "error_message", "document_path", "indexed", "fetched", "extracted", "accepted", "eligible", "chunk_count", "crawl_seconds", "index_seconds"}
        if not fields.keys() <= allowed or status not in {"discovered", "queued", "crawling", "crawled", "failed", "skipped", "rejected"}:
            raise ValueError("Invalid frontier update")
        values = {"status": status, **fields}
        self.db.execute("UPDATE urls SET " + ",".join(f"{key}=?" for key in values) + " WHERE normalized_url=?", (*values.values(), url))
        self.db.commit()

    def next(self, domain, max_depth, *, retry_only=False):
        retry_filter = " AND attempts>0" if retry_only else ""
        row = self.db.execute("SELECT * FROM urls WHERE domain=? AND status='queued' AND depth<=?" + retry_filter + " ORDER BY attempts DESC,depth,rowid LIMIT 1", (domain, max_depth)).fetchone()
        return dict(row) if row else None

    def retry_failed(self):
        self.db.execute("UPDATE urls SET status='queued' WHERE status='failed' OR error_type='robots_unavailable'")
        self.db.commit()

    def stats(self):
        domains = {}
        for row in self.db.execute("SELECT domain,status,COUNT(*) n FROM urls GROUP BY domain,status"):
            domains.setdefault(row["domain"], {})[row["status"]] = row["n"]
        indexed = dict(self.db.execute("SELECT domain,COUNT(*) FROM urls WHERE indexed=1 GROUP BY domain"))
        totals = dict(self.db.execute('''SELECT COUNT(*) discovered_urls, SUM(eligible) eligible_urls,
            SUM(fetched) fetched_urls, SUM(extracted) extracted_pages, SUM(accepted) successful_pages,
            SUM(status='rejected') rejected_pages, SUM(error_type='soft_404') soft_404_pages,
            SUM(error_type='robots') robots_blocked_urls, SUM(status='failed') failed_urls,
            SUM(indexed) successfully_indexed_documents, SUM(chunk_count) chunks,
            SUM(attempts) page_attempts, SUM(crawl_seconds) crawl_seconds,
            SUM(index_seconds) index_seconds FROM urls''').fetchone())
        totals = {key: value or 0 for key, value in totals.items()}
        return {"domains": domains, "indexed_by_domain": indexed,
                "totals": totals,
                "events": dict(self.db.execute("SELECT name,value FROM counters"))}

    def close(self):
        self.db.commit()
        self.db.close()
