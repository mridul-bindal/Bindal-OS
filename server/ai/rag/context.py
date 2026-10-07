"""Deterministic context selection; no retrieval, tokenization or network access."""
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
import math
from typing import Any
from urllib.parse import urlsplit


@dataclass(frozen=True)
class ContextChunk:
    source_id: int
    rank: int
    document_name: str
    title: str | None
    url: str | None
    source: str | None
    domain: str | None
    chunk_id: str | None
    text: str
    bm25_score: float | None
    semantic_score: float | None
    rrf_score: float | None
    reranker_score: float | None


@dataclass(frozen=True)
class RAGContext:
    query: str
    chunks: tuple[ContextChunk, ...]

    def format_context(self) -> str:
        """Source excerpts only; content is evidence, never prompt instructions."""
        return "\n\n".join(
            f"[Source {item.source_id}]\n"
            f"Title: {_line(item.title or item.document_name)}\n"
            f"Document: {_line(item.document_name)}\n"
            f"Source: {_line(item.source or 'Unavailable')}\n"
            f"Domain: {_line(item.domain or 'Unavailable')}\n"
            f"URL: {_line(item.url or 'Unavailable')}\n"
            f"Chunk ID: {_line(item.chunk_id or 'Unavailable (document-level result)')}\n"
            f"Retrieval rank: {item.rank}\n"
            f"Content:\n{item.text}"
            for item in self.chunks
        )

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable evidence, scores and source labels."""
        return {"query": self.query, "chunks": [asdict(c) for c in self.chunks],
                "context": self.format_context()}

    def to_prompt_inputs(self) -> dict[str, str]:
        """Plain variables suitable for a future LangChain prompt template."""
        return {"query": self.query, "context": self.format_context()}


def _line(value: str) -> str:
    return " ".join(value.split())


def _optional_text(item: Mapping, key: str) -> str | None:
    value = item.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string or None")
    return value if value.strip() else None


def _score(item: Mapping, key: str) -> float | None:
    value = item.get(key)
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{key} must be finite and numeric")
    try:
        score = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{key} must be finite and numeric") from None
    if not math.isfinite(score):
        raise ValueError(f"{key} must be finite and numeric")
    return score


def build_context(query: str, results: Sequence[Mapping[str, Any]], *,
                  top_k: int = 5, deduplicate_documents: bool = True) -> RAGContext:
    """Select the first K unique, nonempty results in the supplied reranked order.

    Accept raw reranker dictionaries or serialized API hits (file_name alias).
    Deduplicate chunk IDs within a document and exact text across documents.
    By default, also keep only the first document-name/URL occurrence. Disable
    document deduplication to retain distinct chunks of a single document.
    No re-sorting, rechunking, score thresholds or text truncation occurs.
    """
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string")
    if type(top_k) is not int or top_k <= 0:
        raise ValueError("top_k must be a positive integer")
    if type(deduplicate_documents) is not bool:
        raise ValueError("deduplicate_documents must be a boolean")
    selected = []
    seen_chunks, seen_text, seen_names, seen_urls = set(), set(), set(), set()
    for rank, item in enumerate(results, 1):
        text = _optional_text(item, "text")
        if text is None:
            continue
        name = _optional_text(item, "document_name") or _optional_text(item, "file_name")
        if name is None:
            raise ValueError("A result with text must have a document name")
        chunk_id = _optional_text(item, "chunk_id")
        url = _optional_text(item, "url") or _optional_text(item, "source_url")
        key = (name, chunk_id)
        if text in seen_text or (chunk_id is not None and key in seen_chunks):
            continue
        if deduplicate_documents and (name in seen_names or (url and url in seen_urls)):
            continue
        domain = _optional_text(item, "domain")
        if domain is None and url:
            try:
                domain = urlsplit(url).hostname
            except ValueError:
                pass
        selected.append(ContextChunk(
            source_id=len(selected) + 1, rank=rank, document_name=name,
            title=_optional_text(item, "title"), url=url,
            source=_optional_text(item, "source"), domain=domain,
            chunk_id=chunk_id, text=text,
            **{key: _score(item, key) for key in
               ("bm25_score", "semantic_score", "rrf_score", "reranker_score")},
        ))
        seen_chunks.add(key)
        seen_text.add(text)
        seen_names.add(name)
        if url:
            seen_urls.add(url)
        if len(selected) == top_k:
            break
    return RAGContext(query=query, chunks=tuple(selected))
