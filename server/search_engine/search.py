# Searches documents using direct scanning or inverted indexes, with optional snippets.
from .snippets import create_snippet
from .tokenizer import tokenize


def basic_search(query: str, file_data: dict[str, str]) -> list[str]:
    tokens = set(tokenize(query))
    results = []
    for file_name, file_content in file_data.items():
        tokenized_file_data = set(tokenize(file_content))
        if tokens & tokenized_file_data:
            results.append(file_name)
    return results


def search_with_inverted_index(
    query: str, inverted_index: dict[str, set[str]]
) -> list[str]:
    tokens = set(tokenize(query))
    results = set()
    for token in tokens:
        if token in inverted_index:
            results.update(inverted_index[token])
    return list(results)


def search_ranked_inverted_index(
    query: str, ranked_inverted_index: dict[str, dict[str, int]]
) -> list[str]:
    tokens = set(tokenize(query))
    scores: dict[str, int] = {}
    for token in tokens:
        for file_name, count in ranked_inverted_index.get(token, {}).items():
            scores[file_name] = scores.get(file_name, 0) + count

    ranked_documents = sorted(
        scores.items(),
        key=lambda item: item[1],
        reverse=True,
    )
    return [file_name for file_name, _ in ranked_documents]


def search_tfidf(
    query: str, tfidf_index: dict[str, dict[str, float]]
) -> list[str]:
    """Return documents ranked by the sum of their matching TF-IDF weights."""
    tokens = set(tokenize(query))
    scores: dict[str, float] = {}
    for token in tokens:
        for file_name, weight in tfidf_index.get(token, {}).items():
            scores[file_name] = scores.get(file_name, 0.0) + weight

    ranked_documents = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    return [file_name for file_name, _ in ranked_documents]


def search_ranked_inverted_index_with_snippets(
    query: str,
    ranked_inverted_index: dict[str, dict[str, int]],
    file_data: dict[str, str],
) -> list[dict[str, object]]:
    tokens = set(tokenize(query))
    scores: dict[str, int] = {}
    for token in tokens:
        for file_name, count in ranked_inverted_index.get(token, {}).items():
            scores[file_name] = scores.get(file_name, 0) + count

    ranked_documents = sorted(
        scores.items(),
        key=lambda item: item[1],
        reverse=True,
    )
    return [
        {
            "file_name": file_name,
            "score": score,
            "snippet": create_snippet(file_data[file_name], tokens),
        }
        for file_name, score in ranked_documents
    ]
