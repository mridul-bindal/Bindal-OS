# Controlled corpus growth validation

Validated on 2026-10-04. No 5,000- or 10,000-document crawl was started.

## Changes

- Configurable extraction-quality checks now run before storage/dedup-history
  updates and indexing. Rejections carry reason codes and measured statistics.
- Successful, quality-approved, deduplicated, indexed documents advance the
  target. Pending batches reserve slots so neither global nor domain caps overshoot.
- Separate persistent page-attempt and HTTP-request limits bound unsuccessful work.
- The default target is 5,000 documents, at most 2,500 per domain, with only 50
  additional successes per invocation. CLI options support staged growth.
- Vector projections use observed chunks/document, a configurable conservative
  floor, and actual collection counts when available. Over-budget projections
  stop crawling before discovery; projections refresh after indexing batches.
- Existing qualifying corpus documents count toward the target and are not
  unnecessarily refetched. Failed indexing can resume from saved JSON, including
  a retry-only mode without new URL discovery.
- Reports distinguish extraction, acceptance, rejection, deduplication, failure,
  successful indexing, physical vector growth, timing and corpus totals. Each
  invocation has a separate persisted batch report.

BM25 scoring, semantic retrieval, RRF, cross-encoder ranking, extraction and
chunking algorithms were not changed. The adapter calls the existing indexer.

## Tests

**240 tests passed**, including the previous 215 tests and 25 new growth cases.
Coverage includes quality/rejection reasons, legitimate articles about HTTP errors,
boilerplate, target reservations, balancing, attempt/request limits, vector
estimation, batch resume, existing-corpus accounting, saved-only recovery and
physical point accounting after partial uploads. Automated tests use mocked HTTP.

```powershell
.venv/Scripts/python.exe -m pytest -q -o cache_dir=.pytest_cache_local --basetemp=.pytest_tmp/growth-verified2
```

Only the existing FastAPI/TestClient deprecations and in-memory Qdrant index
warning remained. Whitespace diff checks passed.

## Discovery validation

A live dry run used four sitemap attempts per domain and one HTML sample per
domain. It made 12 site requests, discovered 25,243 eligible MDN URLs and 2,184
eligible GFG URLs, and indexed zero new documents. These are bounded discovery
counts, not a complete census. The earlier expanded eight-sitemap validation
found over 5,000 eligible URLs per source; the production discovery budget is 30.

GFG's direct `/sitemap.xml` still returned 403, while its robots-declared
sitemaps worked. Robots and domain rules were respected.

## Small live batch and recovery

The initial batch was limited to 50 additional successful documents, 300 page
attempts, 200 attempts per domain and 600 HTTP requests. It reached 50 successes.
During an earlier index write, Qdrant disconnected without sending a response,
leaving 25 saved documents marked failed. They did not advance the target.
The crawler continued until 50 other documents had indexed successfully.

Those 25 failed documents were then recovered using `--retry-only`, without
fetching any additional webpages. This was a bounded repair of the original
batch, not a larger crawl. All failures are now resolved.

| Measure | Initial batch | Saved-document recovery | Combined |
| --- | ---: | ---: | ---: |
| Successfully indexed documents | 50 | 25 | 75 |
| Chunks in committed batches | 883 | 501 | 1,384 |
| Page-fetch attempts | 79 | 0 | 79 |
| Website HTTP requests, including discovery | 89 | 0 | 89 |
| Quality rejections | 3 | 0 | 3 |
| Content duplicates skipped | 1 | 0 | 1 |
| Page HTTP failures | 0 | 0 | 0 |
| Documents affected by indexing failure | 25 | 0 | 25 recovered |
| Elapsed seconds | 363.83 | 139.84 | 503.67 |

The three rejections were **one soft-404 and two short pages**. The duplicate
was already stored content. None counted as a successful document. There were
8,505 duplicate URL discoveries, 1,458 external-link rejections and one
robots-disallowed URL in the live frontier.

The collection started at **1,214 points**, reached **2,481** after the first
invocation, and finished at **2,598** after recovery. The first invocation's
physical growth included 384 points from its interrupted write. Recovery
upserted those stable IDs and added the remaining 117 points. Therefore:

```text
2,598 - 1,214 = 1,384 new unique vector points
```

Current reporting uses collection count differences for `vectors_added`, so
partial uploads and idempotent retries are represented accurately. The initial
historical report was created before this accounting improvement; audited net
changes are included in [crawler_growth_statistics.json](crawler_growth_statistics.json).
No points remain unaccounted for by the initial collection plus verified new chunks.

Reproduction commands (reusing the same frontier resumes it):

```powershell
uv run python -m server.crawler.multipage --dry-run --run-dir data/crawler/runs/growth-dry --max-sitemaps-per-domain 4 --discovery-pages-per-domain 1
uv run python -m server.crawler.multipage --run-dir data/crawler/runs/growth-live --batch-documents 50 --max-sitemaps-per-domain 4 --max-attempts-total 300 --max-attempts-per-domain 200 --max-requests 600
uv run python -m server.crawler.multipage --run-dir data/crawler/runs/growth-live --retry-only --batch-documents 25 --max-attempts-total 300 --max-attempts-per-domain 200 --max-requests 600
```

The normal live command above would add another batch if run again. It was not
rerun after recovery.

## Corpus, metadata and API verification

| Quality-approved web corpus | Documents | Chunks |
| --- | ---: | ---: |
| MDN | 59 | 1,192 |
| GFG | 62 | 1,263 |
| Total | 121 | 2,455 |

The qualifying corpus began at 46 documents. Four older documents remain in
storage/search but are excluded from the new target: three fail current quality
checks and one lacks source metadata. No existing documents were deleted.
Including these legacy pages and the original local files, the API now loads
**135 searchable documents**.

The manual validator verified all **75 new documents / 1,384 new chunks** for
saved content hashes, structural blocks, BM25 membership, unique/complete
Qdrant membership, URL/title/source/domain/timestamp/hash/chunk metadata, and
384-dimensional vectors. New chunks comprise 765 MDN and 619 GFG chunks.

Four searches used the real API lifespan, Qdrant, MiniLM, RRF and cross-encoder:

| Query | Expected source | Rank |
| --- | --- | ---: |
| What are the new JavaScript Set methods? | MDN | 1 |
| Locale-sensitive text segmentation with JavaScript Intl.Segmenter | MDN | 1 |
| Remove extra spaces from a string | GFG | 1 |
| Transpose a matrix in a single line in Python | GFG | 1 |

All returned HTTP 200 with source/domain metadata. Full result scores are in
[crawler_growth_validation.json](crawler_growth_validation.json). These are
workflow checks, not a new relevance benchmark.

```powershell
uv run python -m evaluation.validate_crawler --run-dir data/crawler/runs/growth-live --query-set evaluation/crawler_growth_queries.json --output evaluation/crawler_growth_validation.json
```

## Budget and operating notes

The qualifying corpus averages **20.29 chunks/document**. With the configured
floor of 25, the current 5,000-document target projects **124,573 total vectors**,
below the user-adjustable **150,000** estimate budget. This is not a Qdrant plan
capacity claim or a hard storage guarantee. Actual page sizes can differ.

Measured successful indexing averaged 3.70 seconds/document; page processing
averaged 1.06 seconds/attempt, excluding indexing and upfront sitemap discovery.
End-to-end batch times include discovery and failures and are the better guide
for planning another batch.

Quality checks are configurable heuristics; they cannot guarantee relevance or
exclude every marketing/navigation page. Static HTML and one-writer operation
remain the supported model. Qdrant and local files are not one transaction, as
the recovered disconnect demonstrated. The shared BM25 manifest rebuild remains
a scaling cost. Review batch reports before increasing targets or safety limits.

Restart the backend to load the expanded corpus. Larger runs remain manual;
see the [crawler instructions](../server/crawler/README.md).

## Files changed in this phase

- New: `server/crawler/quality.py`, `budget.py`, `index_adapter.py`.
- Updated orchestration/config: `server/crawler/multipage.py`, `config.py`,
  `crawl_config.json`, `frontier.py`, `policy.py`, `discovery.py`, `crawl.py`, `README.md`.
- Tests: `tests/crawler_growth_test.py`; legacy multipage test fixtures explicitly
  disable quality checks to retain their original queue/indexing test scope.
- Validation: `evaluation/validate_crawler.py`, `crawler_growth_queries.json`,
  `crawler_growth_validation.json`, `crawler_growth_statistics.json`, this report.
