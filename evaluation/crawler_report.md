# Controlled crawler validation

Validated on 2026-10-04. The full 10,000-page crawl was **not** run.

## Implementation

The new sequential crawler combines a persistent SQLite frontier, conservative
URL normalization, exact domain restrictions, robots-aware HTTP and redirect
handling, sitemap/index/gzip discovery, HTML-link discovery, balanced selection,
depth/page/discovery limits, dry-run reporting, and explicit failure recovery.

It calls the existing fetch/extract/dedup/save/chunk/BM25/MiniLM/Qdrant functions.
Source/domain metadata now reaches saved JSON, chunks, the BM25 corpus manifest,
Qdrant payloads, semantic results, and final reranked API responses. Qdrant's
internal replacement scope is stored separately as `index_scope`, with legacy
scope cleanup supported. No retrieval scoring, embedding model, extraction,
content normalization/hash algorithm, or chunking strategy was changed.

## Automated tests

**215 passed**, including all pre-existing tests. The 29 additional cases cover
normalization, domains, limits, balancing, depth, frontier persistence/recovery,
sitemaps and gzip, robots/redirects/delays, individual failures, duplicate content,
dry-run behavior, index retries, metadata propagation and legacy scope cleanup.
All automated crawling tests use mocked HTTP; embeddings are mocked and Qdrant
uses its in-memory implementation.

Command:

```powershell
.venv/Scripts/python.exe -m pytest -q -o cache_dir=.pytest_cache_local --basetemp=.pytest_tmp/multipage-final
```

Only existing FastAPI/TestClient deprecation warnings and the expected in-memory
Qdrant payload-index warning remained. Whitespace diff checks also passed.

## Live discovery

Both runs used the configured crawler user-agent, robots rules, a two-second
minimum per-domain delay, and one HTML link-discovery sample per domain. Neither
saved documents nor called embedding/indexing functions.

| Domain | Eligible, 4-sitemap budget | Eligible, 8-sitemap budget | Selected at production caps |
| --- | ---: | ---: | ---: |
| developer.mozilla.org | 25,244 | 43,764 | 5,000 |
| www.geeksforgeeks.org | 2,184 | 6,168 | 5,000 |
| Total | 27,428 | 49,932 | 10,000 |

These are counts within the inspected discovery budgets, not complete site sizes
or guaranteed article counts. The expanded dry run made 20 HTTP requests, recorded
49,755 first discoveries from sitemaps and 197 from page links, detected 597 URL
duplicates, rejected 33 external links, 21 non-page assets and one robots-disallowed
URL. Both robots files were available. GFG's direct `/sitemap.xml` returned 403;
its robots-declared sitemap index and child sitemaps worked. No restriction was
bypassed.

Reproduction:

```powershell
.venv/Scripts/python.exe -m server.crawler.multipage --dry-run --run-dir data/crawler/runs/validation-dry-expanded --max-sitemaps-per-domain 8 --discovery-pages-per-domain 1
```

The initial sandboxed network attempt was blocked by local socket permissions;
the live validation was then executed with approved network access. Its empty
frontier was kept separate from successful runs.

## Small live crawl and indexing

```powershell
.venv/Scripts/python.exe -m server.crawler.multipage --run-dir data/crawler/runs/validation-live --max-pages-total 50 --max-pages-per-domain 25 --max-sitemaps-per-domain 4
```

| Domain | Page attempts | New documents indexed | New chunks |
| --- | ---: | ---: | ---: |
| developer.mozilla.org | 25 | 25 | 431 |
| www.geeksforgeeks.org | 25 | 24 | 644 |
| Total | 50 | 49 | 1,075 |

The GFG MongoDB seed was already stored and was correctly skipped by content
deduplication. There were no page-fetch or indexing failures. The live run made
60 HTTP requests including robots/sitemap discovery and recorded 885 external-link
rejections, one robots rejection, and 5,521 duplicate URL discoveries. It reused
the existing 384-dimensional MiniLM model and `bindal_document_chunks` collection.
The collection now has **1,214 vectors**: 1,075 new plus 139 previously present.

The manual validator checked every newly indexed chunk against the saved
document/manifest for source, domain, title, URL, content hash, crawl timestamp,
text, chunk ID, heading path, token count and chunking configuration. It checked
complete and unique Qdrant chunk membership, sample vector dimensions, structural
blocks, saved content hashes and BM25 document membership.

## Real API searches

The validator started the actual FastAPI lifespan using TestClient, loaded the
combined corpus, connected to real Qdrant, and used the real MiniLM/RRF/cross-encoder
pipeline. The API loaded **60 documents**, including the newly crawled pages.

| Query | Expected source/page | Rank |
| --- | --- | ---: |
| How do CSS color-mix functions create color palettes? | MDN: Creating color palettes with the CSS color-mix() function | 1 |
| Convert a min heap to a max heap | GFG: Convert Min Heap to Max Heap | 1 |
| Broadcast Channel API communication between browser tabs | MDN: Exploring the Broadcast Channel API for cross-tab communication | 1 |
| Find the smallest range containing elements from k sorted lists | GFG: Smallest Range with Elements from k Sorted Lists | 1 |

All four requests returned HTTP 200 and the expected source/domain fields.
These are workflow smoke checks, not a new relevance benchmark. Full result
metadata and scores are in [crawler_validation.json](crawler_validation.json).
Re-run with `python -m evaluation.validate_crawler`; it reads data and performs
searches without fetching or indexing new webpages.

## Limitations and operating notes

- Discovery currently admits all eligible page paths on allowed domains. Sitemaps
  contain home/about/advertising pages as well as articles. MDN's `/en-US/404`
  returned success HTTP status and was indexed with title `Page not found | MDN`.
  Topic/path selection and soft-404 detection remain content-quality improvements;
  existing extraction behavior was intentionally retained.
- Page caps count distinct attempted URLs, including failures and duplicates.
  A 10,000-attempt run may yield fewer than 10,000 unique documents. Source caps
  and round-robin selection prevent one source consuming the other's allocation.
- Static HTML only; no JavaScript rendering. Conservative robots handling fails
  closed on server errors and cross-origin robots redirects.
- One writer is supported. SQLite/JSON and remote Qdrant do not share a transaction.
  `--retry-failed` recovers saved pages and safely finishes partial indexing.
  Existing BM25 corpus rebuilds and manifest rewrites remain a scaling cost.
- Restart a running API after indexing to reload the local corpus. Older documents
  without source labels retain their existing metadata until explicitly reindexed.
- Python 3.10+ is now declared for the Protego 0.7 dependency and the project's
  existing modern type annotations. The dependency lock was regenerated accordingly.

## Files added or updated for this task

| Area | Files |
| --- | --- |
| New crawler modules/config | `server/crawler/config.py`, `crawl_config.json`, `urls.py`, `frontier.py`, `policy.py`, `discovery.py`, `multipage.py` |
| Existing crawler integration | `server/crawler/crawl.py`, `storage.py`, `dedup.py`, `chunking.py`, `indexing.py`, `README.md` |
| Metadata in indexing/retrieval/API | `server/semantic_search/embeddings.py`, `vector_store.py`, `search.py`, `server/hybrid_search/service.py`, `server/api.py` |
| Tests | `tests/multipage_crawler_test.py`, `tests/semantic_search_test.py`, `tests/hybrid_api_test.py` |
| Manual validation/results | `evaluation/validate_crawler.py`, `crawler_validation.json`, `crawler_report.md`, `crawler_discovery.json`, `crawler_live.json` |
| Dependencies/output exclusions | `pyproject.toml`, `uv.lock`, `.gitignore` |

The working tree already contained unrelated frontend/hybrid changes and inaccessible
tracked pytest artifacts; those were not reverted or cleaned up in this task.
Runtime frontiers, saved documents and the crawler index remain Git-ignored.
