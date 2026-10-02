"""Adapt crawler chunks to the shared BM25, embedding and Qdrant indexers."""
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import asdict
import json
from pathlib import Path
from typing import Any

from qdrant_client import QdrantClient

from server.chunking import DEFAULT_CHUNK_WORDS, DEFAULT_CHUNK_OVERLAP_WORDS, chunk_document
from server.search_engine.BM25 import build_bm25_index
from server.semantic_search.embeddings import embed_chunks
from server.semantic_search.vector_store import DEFAULT_COLLECTION, store_chunks
from .chunking import CrawledDocumentChunk
from .dedup import content_hash, write_json_atomic
from .fetch import validate_url

DEFAULT_INDEX_FILE = Path(__file__).resolve().parents[2] / "crawler_index" / "index.json"


def index_crawled_chunks(
    chunks: Sequence[CrawledDocumentChunk],
    *,
    client: QdrantClient,
    collection: str = DEFAULT_COLLECTION,
    index_file: Path = DEFAULT_INDEX_FILE,
    chunk_words: int = DEFAULT_CHUNK_WORDS,
    overlap_words: int = DEFAULT_CHUNK_OVERLAP_WORDS,
    model: Any | None = None,
) -> dict:
    """Upsert complete page revisions and rebuild BM25 using the shared indexer.

    Supply ALL chunks for each supplied URL with their original chunk settings.
    URLs absent from a call remain indexed. A batch may contain one revision per
    URL. The persistent manifest retains page text and metadata for subsequent
    BM25 rebuilds. One writer per manifest/URL is supported. The caller owns client.
    """
    # Delegate configuration validation to the existing chunker.
    chunk_document("", "", chunk_words=chunk_words, overlap_words=overlap_words)
    index_file = Path(index_file)
    previous = json.loads(index_file.read_text(encoding="utf-8")) if index_file.exists() else {
        "documents": {}, "bm25_index": {},
    }
    if not chunks:
        return previous
    grouped = defaultdict(dict)
    for chunk in chunks:
        url = validate_url(chunk.source_url)
        existing = grouped[url].get(chunk.chunk_id)
        if existing is not None and existing != chunk:
            raise ValueError("Conflicting chunks with the same chunk ID")
        grouped[url][chunk.chunk_id] = chunk

    updates = {}
    ordered_chunks = {}
    for url, unique in grouped.items():
        page = list(unique.values())
        first = page[0]
        metadata = (first.document_name, first.content_hash, first.title, first.crawled_at)
        if any((c.document_name, c.content_hash, c.title, c.crawled_at) != metadata for c in page):
            raise ValueError("Supply one consistent document revision per URL")
        try:
            page.sort(key=lambda c: int(c.chunk_id.rsplit("::chunk-", 1)[1]))
        except (IndexError, ValueError) as exc:
            raise ValueError("Invalid chunk ID") from exc
        # Recover document tokens once: overlap belongs to both vectors, not twice to BM25.
        words = page[0].text.split()
        for chunk in page[1:]:
            words.extend(chunk.text.split()[overlap_words:])
        text = " ".join(words)
        expected = chunk_document(first.document_name, text, chunk_words=chunk_words, overlap_words=overlap_words)
        if content_hash(text) != first.content_hash or len(expected) != len(page) or any(
            c.chunk_id != e.chunk_id or c.text.split() != e.text.split()
            for c, e in zip(page, expected)
        ):
            raise ValueError("Incomplete or inconsistent chunks; supply the full page with its original chunk settings")
        ordered_chunks[url] = page
        updates[url] = {"document_name": first.document_name, "text": text,
                        "chunks": [asdict(c) for c in page]}

    documents = {**previous["documents"], **updates}
    names = [document["document_name"] for document in documents.values()]
    if len(names) != len(set(names)):
        raise ValueError("Document identifiers must be unique across URLs")
    # Use the existing BM25 implementation; recompute corpus-wide statistics on updates.
    bm25 = build_bm25_index({d["document_name"]: d["text"] for d in documents.values()})
    for url, page in ordered_chunks.items():
        embedded = embed_chunks(page, model=model)
        store_chunks(client, collection, embedded, source=f"crawler:{url}",
                     chunk_words=chunk_words, overlap_words=overlap_words)
    result = {"documents": documents, "bm25_index": bm25}
    write_json_atomic(index_file, result)
    return result
