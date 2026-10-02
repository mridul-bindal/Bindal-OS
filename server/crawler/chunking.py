"""Adapt crawled HTML blocks to the shared token-aware chunker."""
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from server.chunking import (
    DEFAULT_CHUNK_OVERLAP_WORDS,
    DEFAULT_CHUNK_WORDS,
    DocumentChunk,
    chunk_document,
)
from .dedup import content_hash
from .storage import url_filename


@dataclass(frozen=True)
class CrawledDocumentChunk(DocumentChunk):
    """A DocumentChunk with the originating webpage's metadata."""

    source_url: str
    title: str
    content_hash: str
    crawled_at: str | None = None
    heading_path: tuple[str, ...] = ()
    chunk_index: int = 0
    token_count: int | None = None
    chunking_config: dict | None = None
    source_text: str | None = None
    source_blocks: list[dict] | None = None

    @property
    def url(self):
        return self.source_url


def chunk_crawled_documents(
    documents: Iterable[Mapping[str, object]],
    *,
    chunk_words: int | None = None,
    overlap_words: int = DEFAULT_CHUNK_OVERLAP_WORDS,
    **token_options,
) -> list[CrawledDocumentChunk]:
    """Chunk unique, non-empty crawl results or saved document dictionaries.

    Skip is_duplicate=True and deduplicate normalized content within this call.
    Saved JSON need not contain is_duplicate. Hashes are verified when supplied,
    or generated for older documents. Original extracted text is never normalized
    before chunking. The URL hash plus content hash identifies a page revision,
    preventing collisions between different URLs or revisions of the same URL.
    """
    if chunk_words is not None and chunk_words <= 0:
        raise ValueError("chunk_words must be positive")
    if chunk_words is not None and not 0 <= overlap_words < chunk_words:
        raise ValueError("overlap_words must be non-negative and smaller than chunk_words")
    seen: set[str] = set()
    output: list[CrawledDocumentChunk] = []
    for document in documents:
        if document.get("is_duplicate") is True:
            continue
        text = document.get("text", "")
        if not isinstance(text, str):
            raise ValueError("Crawled document text must be a string")
        if not text.strip():
            continue
        digest = content_hash(text)
        supplied_hash = document.get("content_hash")
        if supplied_hash is not None and supplied_hash != digest:
            raise ValueError("Crawled document content_hash does not match its text")
        if digest in seen:
            continue
        blocks = document.get("blocks")
        if blocks is not None and content_hash("\n".join(b["text"] for b in blocks)) != digest:
            raise ValueError("Structured blocks do not match document text")
        url, title = document.get("url"), document.get("title", "")
        if not isinstance(url, str) or not isinstance(title, str):
            raise ValueError("Crawled document url and title must be strings")
        crawled_at = document.get("crawled_at")
        if crawled_at is not None and not isinstance(crawled_at, str):
            raise ValueError("crawled_at must be a string when supplied")
        name = f"web-{url_filename(url)[:-5]}-{digest}"
        options = dict(token_options)
        if chunk_words is None:
            options["blocks"] = document.get("blocks")
        chunks = chunk_document(name, text, chunk_words=chunk_words, overlap_words=overlap_words, **options)
        output.extend(CrawledDocumentChunk(
            document_name=chunk.document_name,
            chunk_id=chunk.chunk_id,
            text=chunk.text,
            source_url=url,
            title=title,
            content_hash=digest,
            crawled_at=crawled_at,
            heading_path=getattr(chunk, "heading_path", ()),
            chunk_index=int(chunk.chunk_id.rsplit("-", 1)[1]),
            token_count=getattr(chunk, "token_count", None),
            chunking_config=getattr(chunk, "chunking_config", None),
            source_text=text if chunk_words is None else None,
            source_blocks=document.get("blocks") if chunk_words is None else None,
        ) for chunk in chunks)
        seen.add(digest)
    return output


def chunk_crawled_document(
    document: Mapping[str, object],
    *,
    chunk_words: int | None = None,
    overlap_words: int = DEFAULT_CHUNK_OVERLAP_WORDS,
    **token_options,
) -> list[CrawledDocumentChunk]:
    """Single-document convenience wrapper."""
    return chunk_crawled_documents([document], chunk_words=chunk_words, overlap_words=overlap_words, **token_options)
