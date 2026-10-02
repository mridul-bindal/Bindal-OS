"""Build and persist embeddings for the text documents in the data directory."""
import argparse
from pathlib import Path

from server.file_loader import load_files
from server.semantic_search.chunking import (
    DEFAULT_CHUNK_OVERLAP_WORDS,
    DEFAULT_CHUNK_WORDS,
    chunk_documents,
)
from server.semantic_search.embeddings import embed_chunks
from server.semantic_search.vector_store import connect_qdrant, ensure_collection, store_chunks


def build_embedding_database(
    data_directory: Path,
    *,
    chunk_words: int | None = None,
    overlap_words: int = DEFAULT_CHUNK_OVERLAP_WORDS,
    target_chunk_tokens: int = 200,
    max_chunk_tokens: int = 300,
    overlap_tokens: int = 40,
) -> int:
    """Chunk source text files and persist embeddings in the configured Qdrant cluster."""
    file_data = load_files(str(data_directory))
    if not file_data:
        raise RuntimeError(f"No .txt documents found in {data_directory}")

    chunks = chunk_documents(
        file_data,
        chunk_words=chunk_words,
        overlap_words=overlap_words,
        target_chunk_tokens=target_chunk_tokens, max_chunk_tokens=max_chunk_tokens, overlap_tokens=overlap_tokens,
    )
    if not chunks:
        raise RuntimeError(f"No non-empty text documents found in {data_directory}")
    client, collection = connect_qdrant()
    try:
        ensure_collection(client, collection)
        embedded_chunks = embed_chunks(chunks)
        return store_chunks(
            client, collection, embedded_chunks,
            source=str(data_directory.resolve()),
            chunk_words=chunk_words, overlap_words=overlap_words,
        )
    finally:
        client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "data",
    )
    parser.add_argument("--chunk-words", type=int, default=None, help="Explicit legacy compatibility mode")
    parser.add_argument("--target-chunk-tokens", type=int, default=200)
    parser.add_argument("--max-chunk-tokens", type=int, default=300)
    parser.add_argument("--overlap-tokens", type=int, default=40)
    parser.add_argument("--overlap-words", type=int, default=DEFAULT_CHUNK_OVERLAP_WORDS)
    args = parser.parse_args()

    chunk_count = build_embedding_database(
        args.data_dir,
        chunk_words=args.chunk_words,
        overlap_words=args.overlap_words,
        target_chunk_tokens=args.target_chunk_tokens, max_chunk_tokens=args.max_chunk_tokens, overlap_tokens=args.overlap_tokens,
    )
    print(f"Stored {chunk_count} chunks from {args.data_dir} in Qdrant")


if __name__ == "__main__":
    main()
