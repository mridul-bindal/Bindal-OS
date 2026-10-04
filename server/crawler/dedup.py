"""Exact normalized-content hashing and a persistent local hash record."""
import hashlib
import json
import os
from pathlib import Path
import tempfile


def normalize_content(text: str) -> str:
    """Ignore whitespace layout only; retain case, punctuation and word order."""
    return " ".join(text.split())


def content_hash(text: str) -> str:
    return hashlib.sha256(normalize_content(text).encode("utf-8")).hexdigest()


def write_json_atomic(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         suffix=".tmp", delete=False) as output:
            temporary = Path(output.name)
            json.dump(value, output, ensure_ascii=False, indent=2)
            output.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


class ContentHashRecord:
    """Persistent history scoped to an output directory; use one writer at a time.

    Existing document files seed the record, including Phase 1 files. Scanning
    also recovers hashes if a process stopped after saving a document but before
    updating the record. Corrupt records raise instead of silently losing history.
    """

    def __init__(self, output_dir: Path, *, cache: bool = False):
        self.directory = Path(output_dir)
        self.path = self.directory / "content_hashes.json"
        self.cache = cache
        self._cached = None

    def _read(self) -> dict[str, str]:
        if self.cache and self._cached is not None:
            return dict(self._cached)
        records = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}
        if not isinstance(records, dict) or any(
            not isinstance(key, str) or len(key) != 64 or
            any(char not in "0123456789abcdef" for char in key) or not isinstance(value, str)
            for key, value in records.items()
        ):
            raise ValueError("Invalid crawler content hash record")
        for path in sorted(self.directory.glob("*.json")):
            if path == self.path:
                continue
            document = json.loads(path.read_text(encoding="utf-8"))
            records.setdefault(content_hash(document["text"]), document["url"])
        if self.cache:
            self._cached = dict(records)
        return records

    def has_seen(self, text: str) -> bool:
        return content_hash(text) in self._read()

    def records(self) -> dict[str, str]:
        """Return hash -> first URL, including existing documents."""
        return self._read()

    def persist(self, records: dict[str, str]) -> None:
        write_json_atomic(self.path, records)
        if self.cache:
            self._cached = dict(records)
