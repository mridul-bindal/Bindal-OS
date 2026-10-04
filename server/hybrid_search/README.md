# Reciprocal Rank Fusion

## Web application integration

`GET /api/search?q=...` runs lexical and semantic retrieval, RRF, then the cached
cross-encoder. It does not fall back to BM25-only results on a dependency failure;
the API returns 503 instead. The frontend displays the final ranking and opens
local/crawled documents using `/api/document`.

At startup the API combines local `data/*.txt` and the crawler indexing manifest
into one BM25 corpus, opens a shared Qdrant client using the existing `.env`, and
closes that client on shutdown. Models are loaded lazily through their existing
caches, so the first search may take longer. Restart the backend after indexing
new crawler documents to refresh its corpus snapshot.

Query parameters: `top_k=10` (1–50), `candidate_k=20` (1–100), and
`semantic_k=200` (1–1000 chunk candidates). `top_k` cannot exceed `candidate_k`.
The semantic pool is bounded and only documents available in the API's current
corpus are returned. Increase its depth for larger collections where multiple
chunks crowd out document candidates. The response includes original retrieval
scores, RRF/reranker scores, chunk text, and available webpage title/URL.

`reciprocal_rank_fusion` accepts existing ranked outputs and returns document-level
results. It does not load models, connect to Qdrant, or call either retriever.
BM25 and semantic-search implementations remain unchanged.

```python
from server.hybrid_search import reciprocal_rank_fusion

# bm25_results: output of search_bm25_index or search_bm25_index_with_snippets
# semantic_results: output of semantic_search
results = reciprocal_rank_fusion(bm25_results, semantic_results, k=60)
top_five = results[:5]
for result in top_five:
    print(result.document_name, result.rrf_score, result.chunk_id, result.text)
```

Both inputs must be ranked most relevant first. BM25 dictionaries use `file_name`
and `score`; semantic objects use `document_name`, `chunk_id`, `text`, and `score`.
Document names must identify the same documents in both sources. The function
accepts iterables and does not mutate either input.

For semantic results, the first chunk of each document is retained. Since inputs
are ranked, this is its most relevant chunk. Document ranks are then assigned
consecutively starting at 1. Additional chunks do not add votes or consume ranks.
Duplicate BM25 documents similarly retain their first occurrence before ranking.

Each source contributes `1 / (k + rank)` once per document. Missing sources
contribute zero. `k` defaults to 60 and must be finite and non-negative. Raw
BM25/cosine scores do not enter the fusion calculation. Exact RRF ties are ordered
by document name for deterministic output. Semantic score ties retain input order.

Each `HybridSearchResult` contains:

- `document_name`, `rrf_score`
- `bm25_rank`, `semantic_rank` (document ranks)
- `bm25_score` (original score)
- `chunk_id`, `text`, `semantic_score` (best semantic chunk)

Fields for a missing source are `None`. Results are ordered by descending
`rrf_score`; slice the result list to select a final top-K. Both empty inputs
return an empty list. No weighted RRF, reranking, or generation is performed.

Candidate depth matters: this module can only fuse what it receives. Fetching
five semantic chunks need not yield five documents. The small-corpus evaluation
fetches every chunk before document aggregation; it is not a scalability benchmark.

## Evaluation

From the project root:

```powershell
uv run python -m evaluation.evaluate
```

Optional arguments: `--k`, `--queries`, and `--output-dir`. Credentials are read
through the existing Qdrant connection helper. Evaluation is read-only against
Qdrant and writes only local reports. Avoid reindexing during a run.

The fixed [query set](../../evaluation/queries.json) has 40 manual binary relevance
judgments with rationales, based on source text rather than BM25 output. The runner
rebuilds a BM25 index in memory from the local text files and validates cloud chunk
texts, document coverage, and model against that corpus. It checks the cloud payload
snapshot again at the end and records corpus/query hashes for reproducibility.

Outputs in `evaluation/results/`:

- `report.md`: aggregate, category, and per-query metrics.
- `per_query.csv`: one row per query/system, including document rankings.
- `results.json`: full-precision metrics, rankings, RRF results with chunk metadata,
  configuration, timestamp, and corpus fingerprints.

Recall@5 and Recall@10 use unique documents. Reciprocal rank is untruncated and
zero if no relevant document is retrieved; its macro average is MRR. With only
10 documents, full-depth Recall@10 is primarily a coverage check. This small,
subjectively labeled development set is not an independently judged benchmark.
