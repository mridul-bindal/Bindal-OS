"""Build and persist embeddings for the text documents in the data directory."""
import argparse
import json
from dataclasses import asdict
from pathlib import Path

from server.file_loader import load_files
from server.semantic_search.chunking import (
    DEFAULT_CHUNK_OVERLAP_WORDS,
    DEFAULT_CHUNK_WORDS,
    chunk_documents,
)
from server.semantic_search.embeddings import (
    EMBEDDING_DIMENSIONS,
    MODEL_NAME,
    embed_chunks,
)


def build_embedding_file(
    data_directory: Path,
    output_file: Path,
    *,
    chunk_words: int = DEFAULT_CHUNK_WORDS,
    overlap_words: int = DEFAULT_CHUNK_OVERLAP_WORDS,
) -> int:
    """Chunk all source text files, embed them, and write a JSON artifact."""
    file_data = load_files(str(data_directory))
    if not file_data:
        raise RuntimeError(f"No .txt documents found in {data_directory}")

    chunks = chunk_documents(
        file_data,
        chunk_words=chunk_words,
        overlap_words=overlap_words,
    )
    embedded_chunks = embed_chunks(chunks)
    payload = {
        "model": MODEL_NAME,
        "dimensions": EMBEDDING_DIMENSIONS,
        "chunk_words": chunk_words,
        "overlap_words": overlap_words,
        "documents": len(file_data),
        "chunks": [asdict(chunk) for chunk in embedded_chunks],
    }
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")
    return len(embedded_chunks)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "data",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "data" / "embedded_chunks.json",
    )
    parser.add_argument("--chunk-words", type=int, default=DEFAULT_CHUNK_WORDS)
    parser.add_argument("--overlap-words", type=int, default=DEFAULT_CHUNK_OVERLAP_WORDS)
    args = parser.parse_args()

    chunk_count = build_embedding_file(
        args.data_dir,
        args.output,
        chunk_words=args.chunk_words,
        overlap_words=args.overlap_words,
    )
    print(f"Embedded {chunk_count} chunks from {args.data_dir} into {args.output}")


if __name__ == "__main__":
    main()