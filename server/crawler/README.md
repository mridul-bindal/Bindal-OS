# Crawler: single pages and controlled multi-page runs

## Controlled corpus growth

Use Python 3.10+ and `uv sync` from the project root. Qdrant credentials remain
in `server/semantic_search/.env`. Existing BM25, MiniLM, structure-aware chunking,
vector storage, RRF and cross-encoder ranking are reused.

The default configuration targets **5,000 quality-approved indexed documents**,
with at most **2,500 per domain**, but each invocation adds at most **50 new
successful documents**. Nothing starts a 5,000-document crawl automatically.

```powershell
uv run python -m server.crawler.multipage --dry-run --run-dir crawler_runs/quality-discovery --max-sitemaps-per-domain 8
uv run python -m server.crawler.multipage --run-dir crawler_runs/quality-live --batch-documents 50
```

Repeat the live command to add the next batch. Use the same run directory, output
directory and index manifest to resume. A completed URL is not fetched or indexed
again, including URLs found in the existing corpus before this frontier was
created. Failed indexing can be retried from saved documents with `--retry-failed`.
A committed manifest recovers a crash before the frontier was acknowledged.

For recovery without discovering or fetching new URLs, add `--retry-only`.
This retries previously attempted URLs; saved indexing failures need no website
requests. A previously failed HTTP fetch may still need another request.

Change scale without editing source code, for example:

```powershell
uv run python -m server.crawler.multipage --run-dir crawler_runs/quality-live --target-documents 500 --max-documents-per-domain 250 --batch-documents 50
uv run python -m server.crawler.multipage --run-dir crawler_runs/quality-live --target-documents 2000 --max-documents-per-domain 1000 --batch-documents 500
uv run python -m server.crawler.multipage --run-dir crawler_runs/quality-live --target-documents 5000 --max-documents-per-domain 2500 --batch-documents 500
```

These are manual examples, not scheduled jobs. After reviewing statistics, a
10,000 target can likewise use `--target-documents 10000` and
`--max-documents-per-domain 5000`. The configured vector estimate may block that
increase; choose your own budget before increasing it. Corpus targets include
already indexed pages that pass the current quality/metadata checks. Original
local text files are outside the two web-domain targets. Old low-quality or
unlabelled pages remain stored/searchable but are explicitly excluded from the
new successful-document target; this task does not delete existing data.

### Quality checks

`quality.py` runs after extraction and **before saving, hashing history updates,
chunking, embedding or indexing**. Single-page crawling behaves as before unless
its optional `quality_check` callback is supplied. Checks combine text length,
word count, unique vocabulary, repeated lines, navigation-like lines and
boilerplate density. Error-title checks distinguish obvious soft-404/error pages
from tutorials discussing HTTP status codes. They are transparent heuristics,
not a relevance or language model; some low-value pages can still pass.

Rejected pages have structured reason codes (`empty_content`, `too_short`,
`insufficient_content`, `soft_404`, `error_page`, `boilerplate`,
`navigation_content`) and measured values in the frontier. Links on rejected
pages may still discover useful documents. Thresholds live in the `quality`
object of `crawl_config.json`; use `--config path.json` for another configuration.
Previously rejected pages are not automatically revisited on every resume.

### Targets and safety budgets

- `target_documents`: global successful web-document target; default 5,000.
- `max_documents_per_domain`: successful per-domain cap; default 2,500. Selection
  alternates between domains while respecting each cap.
- `batch_documents`: maximum additional successes in this invocation; default 50.
- `index_batch_size`: number of accepted pages sent to the existing indexer per
  write batch; default 25. Pending pages reserve target slots to prevent overshoot.
- `max_attempts_total` / `max_attempts_per_domain`: persistent page-fetch safety
  limits, including retries/failures/duplicates; defaults 20,000 / 10,000. Saved
  document indexing retries do not consume another fetch attempt.
- `max_requests`: persistent HTTP safety limit including robots, sitemap and
  redirect requests; default 50,000. Increase explicitly if a later batch exhausts it.
- `max_vectors_estimate`: user-selected vector estimate budget; default 150,000.
  This is **not** a claim about any Qdrant plan's capacity.
- `estimated_chunks_per_document`: fallback/conservative floor, default 25.

Before discovery, the crawler reports existing successful documents, observed
chunks/document, actual Qdrant points when available, and the projected total:

```text
existing points + remaining target documents * max(observed average, configured estimate)
```

If the projection exceeds the budget, crawling stops before any site requests.
The projection is refreshed after successful indexing batches. It is an estimate,
not a hard Qdrant storage limit: document sizes vary. When point count is
unavailable, local chunk statistics provide a fallback and the report records
that the remote count is unknown. Dry-run does not contact Qdrant, so its estimate
uses local statistics. A small batch still checks the overall selected target.

The deprecated `max_pages_total` / `max_pages_per_domain` configuration keys and
CLI flags retain their old **attempt-cap** meanings. Use the new document-target
options for successful corpus growth.

### Discovery, persistence and reports

Sitemap indexes, nested references, gzip and HTML links share a SQLite frontier.
Exact allowed domains, normalized URL identity, depth limits, robots rules and
sequential per-domain delays apply throughout, including redirect destinations.
[Protego](https://github.com/scrapy/protego) handles robots rules; robots cannot be
disabled. A missing robots file (404/410) allows crawling; other failures fail
closed. External sitemap/redirect targets are rejected. Static HTML only.
Trailing slash and query-order distinctions are retained; fragments and obvious
encoding/host duplicates are normalized. Sitemap pages start at depth zero;
page links increase depth by one. Bounded sitemap/frontier discovery means
eligible counts describe the inspected subset, not a full website census.

A dry run samples limited pages for links but never saves documents or indexes.
Keep dry/live run directories separate. Runs store `frontier.sqlite3`, `mode.json`,
`report.json` and an immutable-per-invocation `batch-NNNN.json` history. Reports
separate discovered/eligible/fetched/extracted/accepted/rejected/indexed pages,
URL/content duplicates, robots blocks, request/index failures and soft-404s.
They include per-domain corpus counts, chunks, averages, vector estimates,
actual points, elapsed time and stop reason. Frontier totals include reconciled
pre-existing documents; `batch` describes only this invocation. Per-page reasons
and error messages are retained in SQLite.

`vectors_added` is the actual collection count delta when both endpoint counts
are available, so it includes partial uploads from a failed batch. `vectors_written`
and `chunks_created` describe successfully committed indexing batches. They may
differ during failures or idempotent recovery. Request and indexing failures are
reported separately. Each recovery invocation has its own batch report.

Runtime data is Git-ignored. Documents remain in `crawler_output/` and the shared
BM25/metadata manifest in `crawler_index/index.json`. Source/domain, URL, title,
crawl timestamp, hash and chunk metadata survive the existing indexing/search
pipeline. Qdrant's separate `index_scope` preserves per-document replacement.
Use one writer. Local JSON/SQLite and Qdrant are not a distributed transaction;
retry saved failed batches to finish synchronization. Shared BM25 corpus rebuilds
and manifest rewrites remain a scaling cost; `index_batch_size` controls how often
that cost occurs. Restart the backend after indexing to reload its corpus.

New growth components: `quality.py`, `budget.py`, and `index_adapter.py`. The
adapter adds receipts/statistics around the existing indexer; it does not replace
any retrieval or indexing algorithm. Unit tests use mocked HTTP and models.
`python -m evaluation.validate_crawler --run-dir <run-dir> --output <report.json>`
performs manual, read-only checks against the real collection and API. An optional
`--query-set` supplies JSON rows `[query, source, expected_url]` for newly added pages.

## Single-page usage

```python
from server.crawler import crawl_url

document = crawl_url("https://example.com/page")
print(document["title"], document["text"])
```

`crawl_url` returns a dictionary with `url`, `title`, `text`, `content_hash`,
`crawled_at`, `blocks`, and `is_duplicate`.
By default it also saves UTF-8 JSON under the project's `crawler_output/`
directory, which is ignored by Git. Pass `output_dir=None` for extraction without
saving, or a `Path` to select another output directory. The timestamp is UTC in
ISO 8601 format. A missing HTML title falls back to the main content's H1, then
an empty string.

The filename is the full SHA-256 hash of the normalized requested URL. Fragments
are discarded; query parameters are preserved. The stored URL remains the request
URL after redirects. New content at the same URL replaces the same document;
previously seen normalized content is skipped, even at a different URL.
Writes use a temporary file and atomic replacement. Failed crawls do not save a
document or overwrite a previous successful crawl.

## Manual demo

From the project root, supply a webpage URL:

```powershell
uv run python -m server.crawler.demo "https://example.com/page" --timeout 20
```

Replace the example URL with the actual page you want to fetch. Optional
`--output-dir` changes the destination. The demo reports the title, extracted
character count, and saved path; failures produce a nonzero exit status.

## Modules and behavior

- `fetch.py`: HTTP(S) validation, redirects, HTTPX requests, and error handling.
- `extract.py`: Beautiful Soup parsing, main-text selection, and whitespace cleanup.
- `storage.py`: deterministic filenames and JSON persistence.
- `dedup.py`: normalization, SHA-256 content hashing, and persistent hash history.
- `crawl.py`: the reusable orchestration function.

An existing `httpx.Client` can be supplied through `client=` for connection reuse
or deterministic mocked tests. The caller owns that client; otherwise `crawl_url`
creates and closes one. Invalid URLs/timeouts raise `ValueError`; network errors,
HTTP failures, non-HTML responses, and pages without usable text raise `CrawlError`.
Storage failures propagate as `OSError`. The default timeout is 20 seconds per
HTTP operation, not a deadline for the whole crawl.

Extraction prefers explicit `articleBody` markup, then `<article>`, `<main>`,
`role="main"`, and the body. For unsemantic layouts, a heading/prose/link-density
heuristic selects a narrower content container. Scripts, styles, navigation, sidebars, footers, forms, hidden elements,
and other obvious non-content elements are removed. Inline punctuation is retained;
prose whitespace is normalized. `<pre>` code retains indentation and internal spaces,
with blank lines removed. Selection is deliberately heuristic, so unusual layouts
may need better extraction in a later phase.

The single-page entry point fetches static HTML only. It does not execute
JavaScript, discover links, recurse, index documents, or call a search/embedding
service. The separate multi-page entry point above adds orchestration.

Unit tests use HTTPX MockTransport and never contact live websites. Implementation
references: [HTTPX](https://www.python-httpx.org/quickstart/) and
[Beautiful Soup](https://www.crummy.com/software/BeautifulSoup/bs4/doc/).

## Phase 2: content deduplication

Normalization collapses whitespace runs (including line endings) to a single
space and trims outer whitespace. Case, punctuation, and word order remain
unchanged. Normalization is used only for hashing: extracted/stored text retains
its original Phase 1 formatting. Whitespace-only changes, including code spacing,
are intentionally considered identical under this policy; this is not code-aware
or semantic equivalence detection.

`content_hashes.json` in each output directory maps SHA-256 hashes to the first
URL seen. It persists across runs. Only successful document writes are recorded.
Duplicate URLs/content leave the first saved document and timestamp unchanged.
Existing Phase 1 documents are recognized by scanning their text; they are not
rewritten. The same scan recovers a saved document if a previous execution stopped
before updating the hash record. Corrupt records raise an error rather than being
silently discarded.

```python
from pathlib import Path
from server.crawler import ContentHashRecord, content_hash, crawl_url

record = ContentHashRecord(Path("crawler_output"))
already_seen = record.has_seen("Some extracted text")
digest = content_hash("Some extracted text")
document = crawl_url("https://example.com/page")
if document["is_duplicate"]:
    print("Skipped duplicate content")
```

`is_duplicate` is `False` when saved, `True` when skipped, and `None` when
`output_dir=None` bypasses persistence and duplicate checking. This status is
returned only; saved JSON contains document metadata and typed HTML blocks. Direct
`save_document` calls also deduplicate and return a saved `Path` or `None`.

The record is historical: old hashes remain seen if a URL later changes or its
file is manually removed. Use a new output directory to start a fresh history.
This lightweight implementation supports sequential executions, with one writer
per output directory; concurrent writers are not supported. Scanning local JSON
files favors simplicity and recovery over scaling to very large crawl archives.

## Phase 3: crawled documents to chunks

```python
from server.crawler import crawl_url
from server.crawler.chunking import chunk_crawled_document, chunk_crawled_documents

document = crawl_url("https://example.com/page")
chunks = chunk_crawled_document(document, target_chunk_tokens=200, max_chunk_tokens=300, overlap_tokens=40)
# Or process several crawl results / saved JSON document dictionaries:
chunks = chunk_crawled_documents([document])
```

The adapter in `chunking.py` calls the existing `server.chunking.chunk_document`;
it does not implement another splitting algorithm. Defaults are a target of 200
tokens, requested maximum of 300, and up to 40 tokens of overlap. The maximum is
capped at MiniLM's actual 256-token input length (including special tokens and
heading context). Each `CrawledDocumentChunk` is a frozen subclass of
`DocumentChunk` and provides `document_name`, `chunk_id`, `text`, `source_url`,
`url` (alias of `source_url`), `title`, `content_hash`, `crawled_at`, `heading_path`,
`chunk_index`, `token_count`, and `chunking_config`. The original `source_text` and
`source_blocks` are retained for validation/indexing, not added to Qdrant payloads.

HTML headings H1-H3, paragraphs, lists, and code are preserved as typed blocks
at extraction time. Heading ancestors prefix child chunks. A section that fits
the effective maximum stays together, even above the target. Larger sections
split at block boundaries, then token offsets for oversized blocks. Code stays
intact when it fits; oversized code prefers line breaks before a token fallback.
Overlap applies only inside split sections and is reduced/omitted when needed
to preserve a whole block and respect the hard budget. Extremely long headings
are shortened in chunk text while their full path remains in metadata.

Plain-text/legacy documents without blocks use paragraph boundaries only; the
adapter does not invent HTML structure from flattened text. Recrawl old webpages
to acquire actual structure. Explicit `chunk_words=` retains the old algorithm
for compatibility, but embedding now rejects over-limit inputs rather than
silently truncating them. New callers should use token settings.

Document identifiers combine the normalized URL's hash and the document content
hash. Chunk IDs use the existing chunker's numbered suffix, giving stable IDs for
each page revision and distinct IDs across different pages and content revisions.
The content hash describes the whole original document, not the individual chunk.

The adapter skips `is_duplicate=True` results before chunking and also keeps only
the first occurrence of each normalized content hash in the supplied batch.
Saved JSON without a duplicate flag is accepted; legacy documents without a hash
get one computed. Supplied hashes must match the document text. Empty/missing text
produces no chunks; malformed non-string text or metadata raises `ValueError`.

Deduplication across separate crawl executions remains Phase 2's responsibility.
Calling this adapter twice on the same saved document intentionally returns the
same chunks; it does not maintain an indexing history or mark anything indexed.
It does not query the crawler hash history, since successfully saved documents
are already present there and still need to be chunked.

This phase stops at returning chunks in memory. No embeddings, index writes,
database calls, or changes to existing crawler/search behavior are introduced.

## Indexing crawler chunks through the shared pipeline

`indexing.index_crawled_chunks` accepts the complete chunks of one or more pages.
It calls the existing `build_bm25_index`, `embed_chunks`, and `store_chunks`.
There are no alternative BM25, embedding, or vector persistence implementations.

```python
from server.crawler.chunking import chunk_crawled_documents
from server.crawler.indexing import index_crawled_chunks
from server.semantic_search.vector_store import connect_qdrant

# documents can be crawl results or loaded saved crawler document dictionaries.
chunks = chunk_crawled_documents(documents)
client, collection = connect_qdrant()
try:
    indexed = index_crawled_chunks(
        chunks, client=client, collection=collection,
    )
finally:
    client.close()

# Directly usable with the unchanged BM25 search function:
from server.search_engine.BM25 import search_bm25_index
hits = search_bm25_index("replication", indexed["bm25_index"])
```

The adapter uses original source text rather than concatenating structural chunks,
so headings and overlap do not inflate BM25 counts. The legacy word-mode adapter
still reconstructs tokens without counting overlap twice. Both pass document-name/text mappings to the original BM25 builder.
The original chunk text, including code whitespace, remains unchanged for
embeddings and Qdrant. Full chunk coverage, hashes, IDs and chunk configuration
are validated before indexing; token settings travel with the chunks.
Repeated identical chunks are ignored. Multiple conflicting revisions of a URL
in one batch are rejected.

The shared embedding representation now carries optional metadata. Local chunks
now include chunking metadata; crawler payloads also retain
`source_url`, `title`, `content_hash`, and `crawled_at`, alongside the existing
`document_name`, `chunk_id`, `text`, `heading_path`, `chunk_index`, token count/config,
and model fields. Vectors use the same MiniLM
model, dimensions, distance, and configured collection.

Each webpage uses a stable Qdrant source scope of `crawler:<normalized URL>`.
The existing store function updates points and removes old generations only
within that URL's scope. Replacing a revision or changing its chunk count removes
stale points without touching other webpages or the local-document pipeline.
Omitted URLs are retained; an empty batch is a no-op, not a deletion request.

`crawler_index/index.json` (Git-ignored) stores the crawler corpus, chunk metadata,
and the BM25 index. `index_file=` can choose another location. Updates replace
that URL's previous document identifier and rebuild BM25 over all known crawler
pages, so obsolete terms and corpus statistics are refreshed. The local-document
BM25 index remains separate and unchanged. Keep this manifest outside the crawler
document output directory. Retain it across runs to preserve BM25 corpus history.

The manifest is replaced atomically after Qdrant uploads succeed. These local and
remote stores do not form a distributed transaction: a partial multi-page failure
can temporarily update Qdrant before BM25. Retrying the same complete batch is
safe and finishes synchronization. Use one writer per manifest/URL. After a failed
indexing attempt, retry from saved crawler JSON/chunks rather than a fresh duplicate
crawl result, since Phase 2 correctly marks that new crawl as already seen.
