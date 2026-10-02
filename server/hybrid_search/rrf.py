"""Standard, unweighted RRF over ranked BM25 documents and semantic chunks."""
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import math
from typing import Protocol


class SemanticHit(Protocol):
    document_name: str
    chunk_id: str
    text: str
    score: float


@dataclass(frozen=True)
class HybridSearchResult:
    document_name: str
    rrf_score: float
    bm25_rank: int | None
    semantic_rank: int | None
    bm25_score: float | None
    chunk_id: str | None
    text: str | None
    semantic_score: float | None


def aggregate_semantic_results(results: Iterable[SemanticHit]) -> list[SemanticHit]:
    """Keep each document's first (best-ranked) chunk, in input rank order.

    Inputs must already be ranked most relevant first, as semantic_search returns.
    Deduplication happens BEFORE assigning consecutive document ranks. Thus extra
    chunks neither add votes nor push other documents down the document ranking.
    Equal-score chunks keep the retriever's original order.
    """
    documents = {}
    for result in results:
        documents.setdefault(result.document_name, result)
    return list(documents.values())


def reciprocal_rank_fusion(
    bm25_results: Iterable[Mapping[str, object]],
    semantic_results: Iterable[SemanticHit],
    *,
    k: float = 60,
) -> list[HybridSearchResult]:
    """Fuse existing retriever outputs without calling or modifying retrievers.

    Ranks start at one. Each unique document receives at most one contribution
    per retriever: 1 / (k + rank). BM25 dictionaries use file_name and score.
    Duplicate BM25 documents retain their first rank/score, then ranks are
    compacted. Missing retrievers contribute zero and have None metadata.
    Exact RRF ties are broken lexicographically by document_name.
    """
    if isinstance(k, bool) or not isinstance(k, (int, float)) or not math.isfinite(k) or k < 0:
        raise ValueError("k must be a finite non-negative number")
    bm25 = {}
    for result in bm25_results:
        bm25.setdefault(result["file_name"], result)
    bm25_ranks = {name: rank for rank, name in enumerate(bm25, 1)}
    semantic = {hit.document_name: hit for hit in aggregate_semantic_results(semantic_results)}
    semantic_ranks = {name: rank for rank, name in enumerate(semantic, 1)}
    fused = []
    for name in bm25.keys() | semantic.keys():
        br, sr = bm25_ranks.get(name), semantic_ranks.get(name)
        hit = semantic.get(name)
        fused.append(HybridSearchResult(
            document_name=name,
            rrf_score=(1 / (k + br) if br is not None else 0)
                      + (1 / (k + sr) if sr is not None else 0),
            bm25_rank=br, semantic_rank=sr,
            bm25_score=float(bm25[name]["score"]) if br is not None else None,
            chunk_id=hit.chunk_id if hit else None,
            text=hit.text if hit else None,
            semantic_score=float(hit.score) if hit else None,
        ))
    return sorted(fused, key=lambda result: (-result.rrf_score, result.document_name))
