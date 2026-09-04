# Converts text into normalized word tokens used by the indexes and searches.
import re


def tokenize(query: str) -> list[str]:
    return re.findall(r"[a-zA-Z0-9]+", query.lower())
