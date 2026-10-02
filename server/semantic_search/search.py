"""Read-only semantic search over the existing MiniLM Qdrant collection."""
import argparse
import json
import math
from dataclasses import asdict, dataclass
from typing import Any

from qdrant_client import QdrantClient

from .embeddings import EMBEDDING_DIMENSIONS, get_embedding_model
from .vector_store import DEFAULT_COLLECTION, connect_qdrant


@dataclass(frozen=True)
class SemanticSearchResult:
    document_name: str
    chunk_id: str
    text: str
    score: float


def semantic_search(
    query: str,
    *,
    client: QdrantClient,
    collection: str = DEFAULT_COLLECTION,
    top_k: int = 5,
    model: Any | None = None,
) -> list[SemanticSearchResult]:
    """Return up to top_k chunks in descending cosine similarity order.

    The caller owns the client and can reuse it across searches and indexing.
    By default, the encoder is the same cached MiniLM instance used by indexing.
    This function never creates collections or changes indexed data. Connection,
    missing-collection, and malformed-payload errors are propagated to the caller.
    """
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string")
    if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k <= 0:
        raise ValueError("top_k must be a positive integer")
    encoder = model if model is not None else get_embedding_model()
    vectors = encoder.encode([query.strip()])
    if len(vectors) != 1:
        raise ValueError("Expected one query embedding")
    vector = [float(value) for value in vectors[0]]
    if len(vector) != EMBEDDING_DIMENSIONS:
        raise ValueError(f"Expected {EMBEDDING_DIMENSIONS}-dimensional query embedding")
    if not all(math.isfinite(value) for value in vector) or not any(vector):
        raise ValueError("Query embedding must be finite and non-zero")
    response = client.query_points(
        collection_name=collection,
        query=vector,
        limit=top_k,
        with_payload=["document_name", "chunk_id", "text"],
        with_vectors=False,
    )
    results = []
    for point in response.points:
        payload = point.payload or {}
        if any(not isinstance(payload.get(key), str)
               for key in ("document_name", "chunk_id", "text")):
            raise ValueError(f"Qdrant point {point.id} is missing required chunk metadata")
        results.append(SemanticSearchResult(
            document_name=payload["document_name"],
            chunk_id=payload["chunk_id"],
            text=payload["text"],
            score=float(point.score),
        ))
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("queries", nargs="+", help="One or more quoted natural-language queries")
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()
    if args.top_k <= 0 or any(not query.strip() for query in args.queries):
        parser.error("Queries must be non-empty and --top-k must be positive")
    client, collection = connect_qdrant()
    try:
        output = [
            {"query": query, "results": [asdict(result) for result in semantic_search(
                query, client=client, collection=collection, top_k=args.top_k,
            )]}
            for query in args.queries
        ]
        print(json.dumps(output, indent=2, ensure_ascii=True))
    finally:
        client.close()


if __name__ == "__main__":
    main()
