"""Split original document text into overlapping, embedding-ready chunks."""
from dataclasses import dataclass
import re


DEFAULT_CHUNK_WORDS = 250
DEFAULT_CHUNK_OVERLAP_WORDS = 40


@dataclass(frozen=True)
class DocumentChunk:
    """A chunk of a source document, retaining its source metadata."""

    document_name: str
    chunk_id: str
    text: str


def chunk_document(
    document_name: str,
    text: str,
    *,
    chunk_words: int = DEFAULT_CHUNK_WORDS,
    overlap_words: int = DEFAULT_CHUNK_OVERLAP_WORDS,
) -> list[DocumentChunk]:
    """Return overlapping chunks as slices of the original text.

    Whitespace and punctuation inside each chunk are never normalized or
    tokenized, keeping the text suitable as direct embedding-model input.
    """
    if chunk_words <= 0:
        raise ValueError("chunk_words must be positive")
    if not 0 <= overlap_words < chunk_words:
        raise ValueError("overlap_words must be non-negative and smaller than chunk_words")

    words = list(re.finditer(r"\S+", text))
    if not words:
        return []

    step = chunk_words - overlap_words
    chunks: list[DocumentChunk] = []
    for chunk_number, start_word in enumerate(range(0, len(words), step)):
        end_word = min(start_word + chunk_words, len(words))
        chunks.append(
            DocumentChunk(
                document_name=document_name,
                chunk_id=f"{document_name}::chunk-{chunk_number}",
                text=text[words[start_word].start() : words[end_word - 1].end()],
            )
        )
        if end_word == len(words):
            break
    return chunks


def chunk_documents(
    file_data: dict[str, str],
    *,
    chunk_words: int = DEFAULT_CHUNK_WORDS,
    overlap_words: int = DEFAULT_CHUNK_OVERLAP_WORDS,
) -> list[DocumentChunk]:
    """Chunk every document returned by ``server.file_loader.load_files``."""
    return [
        chunk
        for document_name, text in file_data.items()
        for chunk in chunk_document(
            document_name,
            text,
            chunk_words=chunk_words,
            overlap_words=overlap_words,
        )
    ]
