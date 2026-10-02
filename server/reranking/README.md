# Cross-encoder reranking

```python
from server.reranking import rerank

final_results = rerank(
    query, rrf_results,
    candidate_k=20, top_k=5,
    model_name="cross-encoder/ms-marco-MiniLM-L6-v2",
    document_metadata=metadata_by_document_name,  # Optional text/URL enrichment
)
```

The function accepts existing RRF dataclasses or result dictionaries. It takes
the first `candidate_k`, scores every query/text pair with the cross-encoder,
sorts descending, and returns up to `top_k` dictionaries. Ties retain RRF order.
An empty input returns an empty list without loading a model. Input objects are
not modified. All candidate fields, including retrieval/RRF scores and available
URL metadata, are preserved; `reranker_score` is added.

The unchanged RRF output has no URL field and BM25-only results lack text. Supply
`document_metadata` keyed by document name to fill missing text and URL/title
fields from your document store. Existing non-null candidate fields take priority.
Candidates still missing text raise `ValueError`; they are never silently omitted.

The default pretrained model is a passage relevance cross-encoder, separate from
the MiniLM embedding model. Models load lazily, with an LRU cache retaining up to
two names. The first use downloads weights if unavailable locally. Pairs are
truncated to 512 tokens by the model; raw scores are ranking signals, not relevance
labels or calibrated probabilities. A compatible scalar-scoring `model=` can be
injected for deterministic tests.

Model/API reference: [Sentence Transformers cross-encoders](https://sbert.net/docs/cross_encoder/pretrained_models.html).

## Evaluation

```powershell
uv run python -m evaluation.rerank --candidate-k 10 --top-k 10
```

This extends the existing evaluation using its saved candidate snapshot at
`evaluation/results/results.json`. It checks the unchanged corpus and manually
defined judgments, recomputes all metrics, and scores the saved RRF candidates.
It does not contact Qdrant or change baseline reports. To refresh upstream
retrieval first, run `python -m evaluation.evaluate`.

Optional flags: `--baseline`, `--queries`, `--output-dir`, `--model`,
`--candidate-k`, `--top-k`. Outputs in `evaluation/reranking_results/` include
aggregate/per-query metrics, full rankings/scores, metric deltas, and categories
for improvements, decreases, mixed changes, unchanged rankings, and rankings
that changed without measurable relevance gains. Recall@10 uses ten results by
default so it is comparable with the baseline; smaller pools or output limits
necessarily cap recall. The ten-document development corpus limits generalization.
