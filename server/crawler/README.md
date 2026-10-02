# Single-page crawler with exact content deduplication

```python
from server.crawler import crawl_url

document = crawl_url("https://example.com/page")
print(document["title"], document["text"])
```

`crawl_url` returns a dictionary with `url`, `title`, `text`, `content_hash`,
`crawled_at`, and `is_duplicate`.
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

Extraction prefers `<main>`, then an element with `role="main"`, then `<article>`,
then the body. Scripts, styles, navigation, sidebars, footers, forms, hidden elements,
and other obvious non-content elements are removed. Inline punctuation is retained;
prose whitespace is normalized. `<pre>` code retains indentation and internal spaces,
with blank lines removed. Selection is deliberately heuristic, so unusual layouts
may need better extraction in a later phase.

This phase fetches static HTML only. It does not execute JavaScript, discover links,
recurse, index documents, or call any search/embedding service.

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
returned only; saved JSON contains the five document metadata fields. Direct
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
chunks = chunk_crawled_document(document, chunk_words=250, overlap_words=40)
# Or process several crawl results / saved JSON document dictionaries:
chunks = chunk_crawled_documents([document])
```

The adapter in `chunking.py` calls the existing `server.chunking.chunk_document`;
it does not implement another splitting algorithm. Defaults remain 250 words
with 40 words of overlap. Each `CrawledDocumentChunk` is a frozen subclass of
`DocumentChunk` and provides `document_name`, `chunk_id`, `text`, `source_url`,
`title`, `content_hash`, and `crawled_at`. Text is passed to the chunker unchanged.

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
chunks = chunk_crawled_documents(documents, chunk_words=250, overlap_words=40)
client, collection = connect_qdrant()
try:
    indexed = index_crawled_chunks(
        chunks, client=client, collection=collection,
        chunk_words=250, overlap_words=40,
    )
finally:
    client.close()

# Directly usable with the unchanged BM25 search function:
from server.search_engine.BM25 import search_bm25_index
hits = search_bm25_index("replication", indexed["bm25_index"])
```

The adapter reconstructs a document's token sequence without counting overlap
twice, then passes document-name/text mappings to the original BM25 builder.
The original chunk text, including code whitespace, remains unchanged for
embeddings and Qdrant. Full chunk coverage, hashes, IDs and chunk configuration
are validated before indexing; pass the same settings used to create the chunks.
Repeated identical chunks are ignored. Multiple conflicting revisions of a URL
in one batch are rejected.

The shared embedding representation now carries optional metadata. Local chunks
continue to produce their existing payloads; crawler payloads also retain
`source_url`, `title`, `content_hash`, and `crawled_at`, alongside the existing
`document_name`, `chunk_id`, `text`, and model fields. Vectors use the same MiniLM
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
