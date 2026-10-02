from collections.abc import Mapping, Sequence
from dataclasses import asdict, is_dataclass
from functools import lru_cache
import math
from typing import Any

DEFAULT_MODEL = "cross-encoder/ms-marco-MiniLM-L6-v2"


@lru_cache(maxsize=2)
def get_reranker_model(model_name: str = DEFAULT_MODEL) -> Any:
    """Load lazily and reuse up to two model instances per process."""
    from sentence_transformers import CrossEncoder
    return CrossEncoder(model_name, max_length=512)


def rerank(query: str, candidates: Sequence, *, candidate_k: int = 20,
           top_k: int = 5, model_name: str = DEFAULT_MODEL, model: Any = None,
           document_metadata: Mapping[str, Mapping] | None = None) -> list[dict]:
    """Score top RRF candidates, preserving metadata in returned dictionaries.

    Accept RRF dataclasses or dictionaries. For BM25-only hits lacking text,
    document_metadata[document_name]['text'] supplies document content. That map
    can also enrich URLs/titles omitted by upstream RRF. Existing non-None fields
    take precedence. Missing text is an error, never silently dropped. Score ties
    retain input order. Model outputs must be one finite scalar per candidate.
    """
    for name, value in (("candidate_k", candidate_k), ("top_k", top_k)):
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"{name} must be a positive integer")
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string")
    if not isinstance(model_name, str) or not model_name.strip():
        raise ValueError("model_name must be non-empty")
    if not candidates:
        return []
    selected = []
    for candidate in candidates[:candidate_k]:
        item = asdict(candidate) if is_dataclass(candidate) else dict(candidate)
        extra = dict((document_metadata or {}).get(item["document_name"], {}))
        extra.update({key: value for key, value in item.items() if value is not None})
        item = {**item, **extra}
        if not isinstance(item.get("text"), str) or not item["text"].strip():
            raise ValueError(f"Missing candidate text for {item['document_name']}")
        selected.append(item)
    encoder = model if model is not None else get_reranker_model(model_name)
    scores = encoder.predict([(query, item["text"]) for item in selected], show_progress_bar=False)
    if len(scores) != len(selected):
        raise ValueError("Expected one reranker score per candidate")
    for item, score in zip(selected, scores):
        if getattr(score, "ndim", 0) != 0:
            raise ValueError("Reranker must return scalar scores")
        value = float(score)
        if not math.isfinite(value):
            raise ValueError("Reranker scores must be finite")
        item["reranker_score"] = value
    return sorted(selected, key=lambda item: -item["reranker_score"])[:top_k]
