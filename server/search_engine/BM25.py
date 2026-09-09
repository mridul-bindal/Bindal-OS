"""BM25 index construction and document ranking."""
import math

from .indexing import build_ranked_inverted_index
from .snippets import create_snippet
from .stopwords import remove_stopword_tokens
from .tokenizer import tokenize


def calculate_document_lengths(file_data: dict[str, str]) -> dict[str, int]:
    """Count indexable (non-stopword) tokens in each document."""
    return {
        file_name: len(remove_stopword_tokens(tokenize(content)))
        for file_name, content in file_data.items()
    }


def calculate_average_document_length(document_lengths: dict[str, int]) -> float:
    if not document_lengths:
        return 0.0
    return sum(document_lengths.values()) / len(document_lengths)


def calculate_bm25_idf(total_docs: int, document_frequency: int) -> float:
    """Return the non-negative, smoothed BM25 inverse-document frequency."""
    if total_docs == 0 or document_frequency == 0:
        return 0.0
    return math.log(1 + (total_docs - document_frequency + 0.5) / (document_frequency + 0.5))


def build_bm25_index(
    file_data: dict[str, str], k1: float = 1.5, b: float = 0.75
) -> dict[str, dict[str, float]]:
    """Build a token-to-document BM25 weight index."""
    if k1 < 0:
        raise ValueError("k1 must be non-negative")
    if not 0 <= b <= 1:
        raise ValueError("b must be between 0 and 1")

    ranked_index = build_ranked_inverted_index(file_data)
    document_lengths = calculate_document_lengths(file_data)
    average_document_length = calculate_average_document_length(document_lengths)
    total_docs = len(file_data)
    bm25_index: dict[str, dict[str, float]] = {}

    for token, document_counts in ranked_index.items():
        idf = calculate_bm25_idf(total_docs, len(document_counts))
        bm25_index[token] = {}
        for file_name, term_frequency in document_counts.items():
            document_length = document_lengths[file_name]
            length_normalizer = (
                1 - b + b * (document_length / average_document_length)
                if average_document_length
                else 1
            )
            saturated_tf = (term_frequency * (k1 + 1)) / (
                term_frequency + k1 * length_normalizer
            )
            bm25_index[token][file_name] = idf * saturated_tf
    return bm25_index


def _query_tokens(query: str) -> set[str]:
    return set(remove_stopword_tokens(tokenize(query)))


def search_bm25_index(
    query: str, bm25_index: dict[str, dict[str, float]]
) -> list[dict[str, object]]:
    """Return matching documents ordered by their combined BM25 score."""
    scores: dict[str, float] = {}
    for token in _query_tokens(query):
        for file_name, weight in bm25_index.get(token, {}).items():
            scores[file_name] = scores.get(file_name, 0.0) + weight

    ranked_docs = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    return [
        {"file_name": file_name, "score": round(score, 4)}
        for file_name, score in ranked_docs
    ]


def search_bm25_index_with_snippets(
    query: str,
    bm25_index: dict[str, dict[str, float]],
    file_data: dict[str, str],
) -> list[dict[str, object]]:
    """Return BM25-ranked documents together with excerpts around query terms."""
    tokens = _query_tokens(query)
    scores: dict[str, float] = {}
    for token in tokens:
        for file_name, weight in bm25_index.get(token, {}).items():
            scores[file_name] = scores.get(file_name, 0.0) + weight

    ranked_docs = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    return [
        {
            "file_name": file_name,
            "score": round(score, 4),
            "snippet": create_snippet(file_data[file_name], tokens),
        }
        for file_name, score in ranked_docs
    ]
