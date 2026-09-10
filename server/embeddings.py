"""Create embeddings from original document-chunk text."""
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from .chunking import DocumentChunk


MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIMENSIONS = 384


@dataclass(frozen=True)
class EmbeddedChunk:
    """A document chunk together with its MiniLM embedding."""

    document_name: str
    chunk_id: str
    text: str
    embedding: list[float]


@lru_cache(maxsize=1)
def get_embedding_model() -> Any:
    """Load MiniLM once per process and return the reusable model instance."""
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(MODEL_NAME)


def embed_chunks(
    chunks: Sequence[DocumentChunk], *, model: Any | None = None
) -> list[EmbeddedChunk]:
    """Embed original chunk text and verify MiniLM's 384-dimensional output."""
    if not chunks:
        return []

    encoder = model if model is not None else get_embedding_model()
    vectors = encoder.encode([chunk.text for chunk in chunks])
    embedded_chunks = [
        EmbeddedChunk(
            document_name=chunk.document_name,
            chunk_id=chunk.chunk_id,
            text=chunk.text,
            embedding=[float(value) for value in vector],
        )
        for chunk, vector in zip(chunks, vectors)
    ]
    if len(embedded_chunks) != len(chunks):
        raise ValueError("The embedding model returned a vector count different from the chunk count")
    if any(len(chunk.embedding) != EMBEDDING_DIMENSIONS for chunk in embedded_chunks):
        raise ValueError(f"Expected {EMBEDDING_DIMENSIONS}-dimensional embeddings")
    return embedded_chunks
