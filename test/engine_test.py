# Tests the search engine's loading, indexing, searching, and snippet behavior.
from server.file_loader import load_files
from server.search_engine.benchmark import measure_time
from server.search_engine.indexing import (
    build_inverted_index,
    build_ranked_inverted_index,
)
from server.search_engine.search import (
    basic_search,
    search_ranked_inverted_index,
    search_ranked_inverted_index_with_snippets,
    search_with_inverted_index,
)
from server.search_engine.snippets import create_snippet
from server.search_engine.saveIndex import save_index
from server.search_engine.tokenizer import tokenize


def test_tokenize_normalizes_text_and_removes_punctuation():
    text = "Hello, MongoDB! Version 7.0"

    assert tokenize(text) == ["hello", "mongodb", "version", "7", "0"]


def test_tokenize_returns_empty_list_for_non_word_text():
    assert tokenize("!@#$%") == []

def test_build_inverted_index_maps_each_word_to_matching_files():
    file_data = {
        "one.txt": "MongoDB database",
        "two.txt": "MongoDB search",
    }

    assert build_inverted_index(file_data) == {
        "mongodb": {"one.txt", "two.txt"},
        "database": {"one.txt"},
        "search": {"two.txt"},
    }


def test_build_inverted_index_does_not_duplicate_a_file_for_repeated_words():
    index = build_inverted_index({"one.txt": "database database database"})

    assert index == {"database": {"one.txt"}}


def test_build_ranked_inverted_index_counts_word_frequency():
    file_data = {
        "one.txt": "database database index",
        "two.txt": "database",
    }

    assert build_ranked_inverted_index(file_data) == {
        "database": {"one.txt": 2, "two.txt": 1},
        "index": {"one.txt": 1},
    }


def test_basic_search_returns_files_matching_any_query_token():
    file_data = {
        "one.txt": "MongoDB database",
        "two.txt": "search engine",
        "three.txt": "unrelated content",
    }

    assert basic_search("database search", file_data) == ["one.txt", "two.txt"]


def test_basic_search_returns_empty_list_for_unknown_or_empty_query():
    file_data = {"one.txt": "MongoDB database"}

    assert basic_search("redis", file_data) == []
    assert basic_search("", file_data) == []


def test_search_with_inverted_index_returns_all_matching_files():
    inverted_index = {
        "mongodb": {"one.txt", "two.txt"},
        "database": {"one.txt"},
    }

    result = search_with_inverted_index("MongoDB database", inverted_index)

    assert sorted(result) == ["one.txt", "two.txt"]


def test_search_with_inverted_index_returns_empty_for_unknown_query():
    assert search_with_inverted_index("redis", {"mongodb": {"one.txt"}}) == []


def test_ranked_search_orders_files_by_matching_frequency():
    ranked_index = {
        "database": {"one.txt": 4, "two.txt": 1},
        "index": {"two.txt": 2},
    }

    assert search_ranked_inverted_index("database index", ranked_index) == [
        "one.txt",
        "two.txt",
    ]


def test_ranked_search_returns_empty_for_unknown_query():
    assert search_ranked_inverted_index("redis", {}) == []


def test_create_snippet_limits_results_and_removes_newlines():
    content = "MongoDB is a database.\nIndexes make database queries faster."

    snippets = create_snippet(
        content,
        {"database"},
        max_snippets=1,
        snippet_window=30,
    )

    assert len(snippets) == 1
    assert "database" in snippets[0].lower()
    assert "\n" not in snippets[0]


def test_ranked_search_with_snippets_returns_file_score_and_snippets():
    file_data = {
        "one.txt": "database database index",
        "two.txt": "database",
    }
    ranked_index = build_ranked_inverted_index(file_data)

    results = search_ranked_inverted_index_with_snippets(
        "database index",
        ranked_index,
        file_data,
    )

    assert results[0]["file_name"] == "one.txt"
    assert results[0]["score"] == 3
    assert results[0]["snippet"]
    assert results[1]["file_name"] == "two.txt"
    assert results[1]["score"] == 1


def test_measure_time_returns_function_result_and_elapsed_time():
    result, elapsed = measure_time(lambda value: value.upper(), "search")

    assert result == "SEARCH"
    assert elapsed >= 0


def test_save_index_creates_a_missing_file(tmp_path):
    index_path = tmp_path / "index.json"

    save_index({"mongodb": {"one.txt"}}, index_path)

    assert index_path.read_text(encoding="utf-8")


def test_save_index_does_not_overwrite_existing_file(tmp_path):
    index_path = tmp_path / "index.json"
    index_path.write_text("existing index", encoding="utf-8")

    save_index({"new": {"file.txt"}}, index_path)

    assert index_path.read_text(encoding="utf-8") == "existing index"
