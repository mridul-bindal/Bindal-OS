"""Compatibility exports for document embeddings."""
from .semantic_search.embeddings import (
    EMBEDDING_DIMENSIONS,
    MODEL_NAME,
    EmbeddedChunk,
    embed_chunks,
    get_embedding_model,
)

__all__ = [
    "EMBEDDING_DIMENSIONS",
    "MODEL_NAME",
    "EmbeddedChunk",
    "embed_chunks",
    "get_embedding_model",
]
