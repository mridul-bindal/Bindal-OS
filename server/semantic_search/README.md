# Embedding database

From the project root, run:

```powershell
uv run python -m server.semantic_search.build_embeddings
```

The builder uses structure/token-aware chunking with the unchanged MiniLM
model. It reads `QDRANT_URL` and `QDRANT_API_KEY` from the `.env` beside this file.
Environment variables override the file. Optional `QDRANT_COLLECTION` defaults to
`bindal_document_chunks`; the existing `cluster_name` is a cloud cluster label,
not a collection setting.

Vectors are stored in a 384-dimensional cosine collection with original text,
document name, chunk ID, model, source directory, and chunking parameters.
No embedding JSON file is written. Existing JSON artifacts are left untouched.

Use `--data-dir`, `--target-chunk-tokens` (200), `--max-chunk-tokens` (300), and
`--overlap-tokens` (40). The effective maximum is capped by the embedding model's
256-token limit, including special tokens. Plain text uses paragraph boundaries;
crawler HTML supplies typed blocks. `--chunk-words` explicitly selects the legacy
compatibility path; it is no longer the default and over-limit embeddings fail.
Stable IDs update existing chunks; after successful uploads, stale chunks from
the same source directory are removed, including chunks of deleted documents.
An empty input directory is rejected to avoid accidentally clearing an index.
Run only one builder per source directory at a time. Uploads are batched and are
not an atomic snapshot; a failed run can be retried to finish synchronization.
Changing the absolute source directory creates a separate source in the collection.

## Semantic search

From the project root:

```powershell
uv run python -m server.semantic_search.search "How does MongoDB recover when a primary fails?" --top-k 3
```

Pass multiple quoted queries to search them using one connection and the same
cached MiniLM model. The CLI reads the same `.env` settings as the builder and
prints JSON containing `document_name`, `chunk_id`, `text`, and `score` per hit.
`--top-k` defaults to 5 and must be a positive integer. Empty queries are rejected.

For Python callers, pass the existing client to reuse its connection:

```python
from server.semantic_search.search import semantic_search
from server.semantic_search.vector_store import connect_qdrant

client, collection = connect_qdrant()  # Once at application startup
try:
    results = semantic_search(
        "How can I speed up slow MongoDB queries?",
        client=client, collection=collection, top_k=3,
    )
    for result in results:
        print(result.document_name, result.chunk_id, result.score, result.text)
finally:
    client.close()  # At application shutdown, after all searches
```

Search uses the indexing model's cached `get_embedding_model()` and validates a
384-dimensional query vector. It performs read-only queries against the existing
collection through Qdrant's [query_points API](https://qdrant.tech/documentation/search/search/).
Results are chunks ordered by decreasing cosine similarity; scores are not
probabilities. Multiple chunks may belong to the same document. Fewer than K
results are returned if the collection has fewer points. Backend errors are
propagated; searching never creates a missing collection or rebuilds the index.

BM25 remains separate and unchanged. This module adds no hybrid search, RRF,
reranking, RAG, LLM integration, or crawler.
