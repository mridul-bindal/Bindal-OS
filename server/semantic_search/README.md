# Embedding database

From the project root, run:

```powershell
uv run python -m server.semantic_search.build_embeddings
```

The builder retains the temporary overlapping word chunking strategy and MiniLM
model. It reads `QDRANT_URL` and `QDRANT_API_KEY` from the `.env` beside this file.
Environment variables override the file. Optional `QDRANT_COLLECTION` defaults to
`bindal_document_chunks`; the existing `cluster_name` is a cloud cluster label,
not a collection setting.

Vectors are stored in a 384-dimensional cosine collection with original text,
document name, chunk ID, model, source directory, and chunking parameters.
No embedding JSON file is written. Existing JSON artifacts are left untouched.

Use `--data-dir`, `--chunk-words`, and `--overlap-words` to override defaults.
Stable IDs update existing chunks; after successful uploads, stale chunks from
the same source directory are removed, including chunks of deleted documents.
An empty input directory is rejected to avoid accidentally clearing an index.
Run only one builder per source directory at a time. Uploads are batched and are
not an atomic snapshot; a failed run can be retried to finish synchronization.
Changing the absolute source directory creates a separate source in the collection.

The BM25 search flow is unchanged. Stored vectors can be retrieved or searched
with the Qdrant client `query_points` API using MiniLM query embeddings.
