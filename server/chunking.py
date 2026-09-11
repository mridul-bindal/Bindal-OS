"""Compatibility exports for document chunking."""
from .semantic_search.chunking import (
    DEFAULT_CHUNK_OVERLAP_WORDS,
    DEFAULT_CHUNK_WORDS,
    DocumentChunk,
    chunk_document,
    chunk_documents,
)

__all__ = [
    "DEFAULT_CHUNK_OVERLAP_WORDS",
    "DEFAULT_CHUNK_WORDS",
    "DocumentChunk",
    "chunk_document",
    "chunk_documents",
]
