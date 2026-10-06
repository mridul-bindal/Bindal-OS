"""Deterministic token counter for unit tests; real MiniLM is checked in live validation."""
import re
import pytest


class TestTokenCounter:
    model_limit = 256

    def offsets(self, text):
        return [(m.start(), m.end()) for m in re.finditer(r"\S+", text)]

    def count(self, text):
        return len(self.offsets(text)) + 2


@pytest.fixture(autouse=True)
def no_model_download_for_chunking(monkeypatch):
    monkeypatch.setattr("server.semantic_search.structured_chunking.get_token_counter", lambda: TestTokenCounter())
