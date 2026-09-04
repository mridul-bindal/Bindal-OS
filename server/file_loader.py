# Loads text documents from the data directory for the search engine.
import os


def load_files(path: str) -> dict[str, str]:
    file_data = {}
    for file_name in os.listdir(path):
        full_path = os.path.join(path, file_name)
        if os.path.isfile(full_path) and file_name.lower().endswith(".txt"):
            with open(full_path, "r", encoding="utf-8") as file:
                file_data[file_name] = file.read()
    return file_data
