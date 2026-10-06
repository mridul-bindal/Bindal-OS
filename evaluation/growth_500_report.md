# 500-document batch results

The requested command completed with `stop_reason: batch_complete` and exactly
**500 additional successfully indexed documents**. The README was checked before
execution. Existing quality checks, robots rules, two-second per-domain delay,
balanced scheduling and configured safety budgets remained enabled.

```powershell
uv run python -m server.crawler.multipage --run-dir data/crawler/runs/growth-500 --batch-documents 500 --max-sitemaps-per-domain 30
```

No additional crawl or recovery invocation was needed. No retrieval algorithms
or crawler implementation were changed for this operational run.

## Before and after

| Measure | Before | After | Added |
| --- | ---: | ---: | ---: |
| Quality-approved indexed web documents | 121 | 621 | 500 |
| Chunks in that qualifying corpus | 2,455 | 9,543 | 7,088 |
| Qdrant collection points | 2,598 | 9,686 | 7,088 |
| Average chunks per qualifying document | 20.29 | 15.37 | — |
| All documents loaded by the API | 135 | 635 | 500 |

The new batch averaged **14.18 chunks/document**, lower than the earlier sample.
That explains why the total is below the tentative 12,000–13,000-chunk estimate.
The API count includes the original local files and four retained legacy web
documents that do not count toward the current quality-approved target.

| Source | New documents | New chunks | Qualifying documents after | Qualifying chunks after |
| --- | ---: | ---: | ---: | ---: |
| MDN | 249 | 2,070 | 308 | 3,262 |
| GeeksforGeeks | 251 | 5,018 | 313 | 6,281 |
| Total | 500 | 7,088 | 621 | 9,543 |

## Outcomes and timing

- Page attempts/fetched pages: **504**.
- Successful new documents: **500**.
- Page-fetch failures: **0**; indexing failures: **0**; unresolved failures: **0**.
- Duplicate content skipped: **1**.
- Quality rejections: **3** — one soft-404 and two short pages.
- Website HTTP requests, including discovery: **548**.
- Robots-blocked URLs: **1**.
- Repeated URL discoveries ignored: **140,190**. These are repeated link/sitemap
  discoveries, not duplicate stored documents.
- Elapsed time: **2,002.12 seconds**, approximately **33 minutes 22 seconds**.
- Average page processing: **1.05 seconds/attempt**, excluding indexing and
  upfront discovery. Average successful indexing: **2.65 seconds/document**.

One discovery request failed: GFG's direct `/sitemap.xml` returned 403, as in the
earlier validation. Its robots-declared sitemaps worked, so the batch continued
without bypassing the restriction. This is separate from the zero page-fetch and
indexing failures above.

## Qdrant usage and budget

The configured collection now contains **9,686 points**, using the existing
384-dimensional embeddings. All 7,088 additions were matched to the new chunks;
there are no unexplained net point additions from this run.

The raw float32 vector values alone would occupy approximately **14.19 MiB**
(`9,686 × 384 × 4` bytes). This is an arithmetic estimate, **not measured Qdrant
RAM/disk usage**; it excludes payloads, indexes and storage overhead. Actual
server storage, RAM and plan-quota usage were not measured.

The current projection for the configured 5,000-document target is **119,161
total points**, below the configurable **150,000 estimate budget**. The estimate
uses the conservative floor of 25 chunks per remaining document. This budget is
not a statement of Qdrant plan capacity. The run stopped after its 500 successes;
it did not continue toward 5,000.

## Verification

The manual validator checked all **500 new documents / 7,088 chunks** for saved
hashes, structural blocks, BM25 membership, complete and unique Qdrant membership,
source/domain/URL/title/timestamp/hash/chunk metadata, and vector dimensions.

Real API searches used the existing semantic + BM25 + RRF + cross-encoder pipeline:

| Query | Expected page rank |
| --- | ---: |
| How can Git stash help manage unfinished work? | 1 |
| Conditional CI/CD pipelines in GitLab | 1 |
| The lazy caterer's problem | 1 |
| Iterators in C++ STL | 1 |

All four returned HTTP 200. The API loaded **635 documents**. Restart an already
running backend to load the expanded corpus.

Artifacts:

- [Machine-readable before/after statistics](growth_500_statistics.json)
- [Full API verification results](growth_500_validation.json)
- [Starting corpus snapshot](growth_500_before.json)
- [Validation queries](growth_500_queries.json)
- Runtime frontier and full batch report: `data/crawler/runs/growth-500/` (Git-ignored).

Reusing the crawl command will add another batch; it should not be run merely to
view this report. Read-only verification is available with:

```powershell
uv run python -m evaluation.validate_crawler --run-dir data/crawler/runs/growth-500 --query-set evaluation/growth_500_queries.json --output evaluation/growth_500_validation.json
```
