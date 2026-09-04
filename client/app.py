# Console frontend: loads the search data and displays ranked results.
from pathlib import Path
from collections.abc import Callable

from server import load_files
from server.search_engine import (
    build_inverted_index,
    build_ranked_inverted_index,
    build_tfidf_index,
    remove_stopwords,
    save_index,
    search_ranked_inverted_index_with_snippets,
    search_tfidf,
)
from server.search_engine.benchmark import measure_time


QUERIES = [
    "The MongoDB when the documents collections",
    "insertOne updateMany deleteOne",
    "compound indexes explain plans",
    "aggregation pipeline match group sort",
    "embedding referencing schema validation",
    "replica set primary secondary write concern",
    "shard key mongos chunks",
    "authentication authorization encryption",
    "backup recovery monitoring replication lag",
]


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
    search_methods: dict[str, Callable[[str], list[dict[str, object]]]] = {
        "ranked_inverted_index_with_snippets": lambda query: (
            search_ranked_inverted_index_with_snippets(
                query, ranked_inverted_index, file_data
            )
        ),
        "tfidf": lambda query: search_tfidf(query, tfidf_index),
    }

    for query in QUERIES:
        cleaned_query = remove_stopwords(query)
        print(f"QUERY AFTER STOPWORD REMOVAL : {cleaned_query}")
        for search_method, search_function in search_methods.items():
            result, time_taken = measure_time(search_function, cleaned_query)
            print(f"METHOD_NAME : {search_method}")
            print(f"TIME_TAKEN : {time_taken}")
            print("QUERY :", cleaned_query)
            for item in result:
                if isinstance(item, dict):
                    print(f"FILE_NAME : {item['file_name']}")
                    print(f"SNIPPET : {item['snippet']}")
                else:
                    print(f"FILE_NAME : {item}")
                print("-" * 100)
            print("-" * 100)
