import math

from .indexing import build_ranked_inverted_index


def calculate_idf(total_docs: int, frequency: int) -> float:
    if total_docs == 0:
        return 0
    return math.log((total_docs + 1) / (1 + frequency))


def build_tfidf_index(file_data: dict[str, str]) -> dict[str, dict[str, float]]:
    ranked_index = build_ranked_inverted_index(file_data)
    total_docs = len(file_data)
    tfidf_index: dict[str, dict[str, float]] = {}
    for token, document_counts in ranked_index.items():
        frequency = len(document_counts)
        idf = calculate_idf(total_docs, frequency)
        tfidf_index[token] = {}
        for file_name, term_frequency in document_counts.items():
            tfidf = term_frequency * idf
            tfidf_index[token][file_name] = tfidf
    return tfidf_index
