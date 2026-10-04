"""Qdrant persistence for MiniLM document chunks."""
import os
from collections.abc import Sequence
from pathlib import Path
from uuid import NAMESPACE_URL, uuid4, uuid5

from dotenv import load_dotenv
from qdrant_client import QdrantClient, models

from .embeddings import EMBEDDING_DIMENSIONS, MODEL_NAME, EmbeddedChunk

DEFAULT_COLLECTION = "bindal_document_chunks"
ENV_FILE = Path(__file__).with_name(".env")


def connect_qdrant() -> tuple[QdrantClient, str]:
    """Read the adjacent .env; explicit environment variables take precedence."""
    load_dotenv(ENV_FILE)
    url = os.getenv("QDRANT_URL", "").strip()
    api_key = os.getenv("QDRANT_API_KEY", "").strip()
    if not url or not api_key:
        raise ValueError("Set QDRANT_URL and QDRANT_API_KEY in server/semantic_search/.env")
    collection = os.getenv("QDRANT_COLLECTION", DEFAULT_COLLECTION).strip()
    if not collection:
        raise ValueError("QDRANT_COLLECTION must not be empty")
    return QdrantClient(url=url, api_key=api_key, timeout=60), collection


def ensure_collection(client: QdrantClient, collection: str) -> None:
    """Create a collection or reject an incompatible existing vector schema."""
    if not client.collection_exists(collection):
        client.create_collection(
            collection_name=collection,
            vectors_config=models.VectorParams(
                size=EMBEDDING_DIMENSIONS, distance=models.Distance.COSINE
            ),
        )
    info = client.get_collection(collection)
    vectors = info.config.params.vectors
    if not isinstance(vectors, models.VectorParams) or (
        vectors.size != EMBEDDING_DIMENSIONS or vectors.distance != models.Distance.COSINE
    ):
        raise ValueError(f"Collection {collection!r} must use unnamed 384-dimensional cosine vectors")
    # Qdrant Cloud strict mode requires indexes for payload filters.
    for field in ("source", "index_scope", "indexer", "generation"):
        if field not in info.payload_schema:
            client.create_payload_index(
                collection_name=collection,
                field_name=field,
                field_schema=models.PayloadSchemaType.KEYWORD,
                wait=True,
            )


def store_chunks(
    client: QdrantClient,
    collection: str,
    chunks: Sequence[EmbeddedChunk],
    *,
    source: str,
    chunk_words: int | None = None,
    overlap_words: int | None = None,
    batch_size: int = 100,
) -> int:
    """Upsert chunks with stable IDs, awaiting each batch before returning."""
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    if any(len(chunk.embedding) != EMBEDDING_DIMENSIONS for chunk in chunks):
        raise ValueError("Expected 384-dimensional embeddings")
    ensure_collection(client, collection)
    generation = str(uuid4())
    for offset in range(0, len(chunks), batch_size):
        client.upsert(
            collection_name=collection,
            wait=True,
            points=[
                models.PointStruct(
                    id=str(uuid5(NAMESPACE_URL, f"{source}::{chunk.chunk_id}")),
                    vector=chunk.embedding,
                    payload={
                        **{key: value for key, value in chunk.metadata.items()
                           if key in {"source_url", "url", "title", "content_hash", "crawled_at", "domain", "heading_path", "chunk_index", "token_count", "chunking_config"}},
                        "source": chunk.metadata.get("source") or source,
                        "index_scope": source,
                        "indexer": "bindal_semantic_search",
                        "generation": generation,
                        "document_name": chunk.document_name,
                        "chunk_id": chunk.chunk_id,
                        "text": chunk.text,
                        "model": MODEL_NAME,
                        "chunk_words": chunk_words,
                        "overlap_words": overlap_words,
                    },
                )
                for chunk in chunks[offset : offset + batch_size]
            ],
        )
    # Only remove this indexer's stale chunks after every upload has succeeded.
    client.delete(
        collection_name=collection,
        points_selector=models.FilterSelector(filter=models.Filter(
            must=[
                models.FieldCondition(key="indexer", match=models.MatchValue(value="bindal_semantic_search")),
            ],
            # Include the legacy scope field so old page revisions are replaced too.
            should=[models.FieldCondition(key=key, match=models.MatchValue(value=source))
                    for key in ("index_scope", "source")],
            must_not=[models.FieldCondition(
                key="generation", match=models.MatchValue(value=generation)
            )],
        )),
        wait=True,
    )
    return len(chunks)
