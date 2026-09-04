# Console frontend: loads the search data and displays ranked results.
from pathlib import Path
from collections.abc import Callable

from server import load_files
from server.search_engine import (
    build_inverted_index,
    build_ranked_inverted_index,
    save_index,
    search_ranked_inverted_index_with_snippets,
)
from server.search_engine.benchmark import measure_time


QUERIES = [
    "MongoDB documents collections",
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
    save_index(inverted_index, data_path / "inverted_index.json")
    ranked_inverted_index = build_ranked_inverted_index(file_data)
    save_index(ranked_inverted_index, data_path / "ranked_inverted_index.json")
    search_methods: dict[str, Callable[[str], list[dict[str, object]]]] = {
        "ranked_inverted_index_with_snippets": lambda query: (
            search_ranked_inverted_index_with_snippets(
                query, ranked_inverted_index, file_data
            )
        )
    }

    for query in QUERIES:
        print(f"QUERY : {query}")
        for search_method, search_function in search_methods.items():
            result, time_taken = measure_time(search_function, query)
            print(f"METHOD_NAME : {search_method}")
            print(f"TIME_TAKEN : {time_taken}")
            print("QUERY :", query)
            for item in result:
                print(f"FILE_NAME : {item['file_name']}")
                print(f"SNIPPET : {item['snippet']}")
                print("-" * 100)
            print("-" * 100)
