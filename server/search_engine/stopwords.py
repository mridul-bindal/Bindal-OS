try:
    from stopwords import get_stopwords
except ImportError:
    get_stopwords = None


if get_stopwords is not None:
    STOPWORDS = set(get_stopwords("english"))
else:
    STOPWORDS = {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "that",
        "the",
        "this",
        "to",
        "was",
        "were",
        "with",
    }

def remove_stopwords(query: str) -> str:
    tokens = query.split()
    filtered_tokens = [token for token in tokens if token.lower() not in STOPWORDS]
    return " ".join(filtered_tokens)
