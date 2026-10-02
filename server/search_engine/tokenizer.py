"""Shared technical terms plus bounded formatting aliases, never a name dictionary."""
import re
import unicodedata
from .stopwords import STOPWORDS

TOKENIZATION_VERSION = "technical-v2"
_TERM = re.compile(r"(?:\$|\.)?[^\W_]+(?:[._-][^\W_]+)*(?:\+\+|#)?", re.UNICODE)


def tokenize(query: str) -> list[str]:
    text = unicodedata.normalize("NFC", query).casefold()
    matches = list(_TERM.finditer(text))
    tokens = []
    for match in matches:
        term = match.group()
        tokens.append(term)
        if term[0].isalnum() and term[-1].isalnum() and any(c in term for c in "._-"):
            parts = re.split(r"[._-]", term)
            if any(any(c.isalpha() for c in part) for part in parts):
                tokens.extend(dict.fromkeys([*parts, "".join(parts)]))
    for left, right in zip(matches, matches[1:]):
        a, b = left.group(), right.group()
        gap = text[left.end():right.start()]
        if (a != b and a.isalnum() and b.isalnum() and a not in STOPWORDS and b not in STOPWORDS
                and any(c.isalpha() for c in a + b) and min(len(a), len(b)) >= 2
                and len(a + b) <= 48 and gap and gap.isspace() and '\n' not in gap and '\r' not in gap):
            tokens.append(a + b)
    return tokens
