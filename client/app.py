from collections.abc import Callable
from pathlib import Path

from server import load_files
from server.search_engine import (
    basic_search,
    build_bm25_index,
    build_inverted_index,
    build_ranked_inverted_index,
    build_tfidf_index,
    remove_stopwords,
    save_index,
    search_bm25_index,
    search_ranked_inverted_index,
    search_tfidf,
    search_with_inverted_index,
)
from server.search_engine.benchmark import measure_time


QUERY = "replica set primary secondary write concern"


def _format_results(results: list[object]) -> str:
    """Format document names and ranking scores for one table cell."""
    formatted_results = []
    for position, result in enumerate(results, start=1):
        if isinstance(result, dict):
            file_name = str(result["file_name"])
            score = result.get("score")
            formatted_results.append(f"{position}. {file_name} ({score})")
        else:
            formatted_results.append(f"{position}. {result}")
    return "; ".join(formatted_results) or "No matches"


def _print_comparison_table(
    comparisons: list[tuple[str, float, list[object]]],
) -> None:
    headers = ("Algorithm", "Time (ms)", "Ranked results")
    rows = [
        (algorithm, f"{elapsed * 1_000:.4f}", _format_results(results))
        for algorithm, elapsed, results in comparisons
    ]
    widths = [
        max(len(headers[column]), *(len(row[column]) for row in rows))
        for column in range(len(headers))
    ]
    separator = "+" + "+".join("-" * (width + 2) for width in widths) + "+"

    print(separator)
    print("|" + "|".join(f" {headers[i]:<{widths[i]}} " for i in range(3)) + "|")
    print(separator)
    for row in rows:
        print("|" + "|".join(f" {row[i]:<{widths[i]}} " for i in range(3)) + "|")
    print(separator)


def run(data_path: Path | None = None) -> None:
    if data_path is None:
        data_path = Path(__file__).resolve().parent.parent / "data"

    file_data = load_files(str(data_path))
    inverted_index = build_inverted_index(file_data)
    save_index(inverted_index, data_path / "inverted_index.json", overwrite=True)
    ranked_inverted_index = build_ranked_inverted_index(file_data)
    save_index(
        ranked_inverted_index,
        data_path / "ranked_inverted_index.json",
        overwrite=True,
    )
    tfidf_index = build_tfidf_index(file_data)
    save_index(tfidf_index, data_path / "tfidf_index.json", overwrite=True)
    bm25_index = build_bm25_index(file_data)
    save_index(bm25_index, data_path / "bm25_index.json", overwrite=True)
    search_methods: dict[str, Callable[[str], list[object]]] = {
        "Basic search": lambda query: basic_search(query, file_data),
        "Inverted index": lambda query: search_with_inverted_index(
            query, inverted_index
        ),
        "Ranked inverted index": lambda query: search_ranked_inverted_index(
            query, ranked_inverted_index
        ),
        "tfidf": lambda query: search_tfidf(query, tfidf_index),
        "BM25": lambda query: search_bm25_index(query, bm25_index),
    }

    cleaned_query = remove_stopwords(QUERY)
    comparisons: list[tuple[str, float, list[object]]] = []
    for algorithm, search_function in search_methods.items():
        results, elapsed = measure_time(search_function, cleaned_query)
        comparisons.append((algorithm, elapsed, results))

    print(f"Query: {QUERY}")
    print(f"After stopword removal: {cleaned_query}")
    _print_comparison_table(comparisons)
