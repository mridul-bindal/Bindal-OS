# Builds inverted indexes that map words to documents and track word frequency.
from .tokenizer import tokenize
from .stopwords import remove_stopword_tokens


def build_inverted_index(file_data: dict[str, str]) -> dict[str, set[str]]:
    inverted_index = {}

    for file_name, file_content in file_data.items():
        tokens = set(remove_stopword_tokens(tokenize(file_content)))
        for token in tokens:
            inverted_index.setdefault(token, set()).add(file_name)

    return inverted_index


def build_ranked_inverted_index(
    file_data: dict[str, str],
) -> dict[str, dict[str, int]]:
    ranked_index = {}
    for file_name, file_content in file_data.items():
        for token in remove_stopword_tokens(tokenize(file_content)):
            ranked_index.setdefault(token, {}).setdefault(file_name, 0)
            ranked_index[token][file_name] += 1
    return ranked_index
