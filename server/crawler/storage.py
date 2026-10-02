"""Stable, atomic local JSON storage."""
import hashlib
from pathlib import Path

from .fetch import validate_url
from .dedup import ContentHashRecord, content_hash, write_json_atomic

DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parents[2] / "crawler_output"


def url_filename(url: str) -> str:
    return hashlib.sha256(validate_url(url).encode("utf-8")).hexdigest() + ".json"


def save_document(document: dict, output_dir: Path = DEFAULT_OUTPUT_DIR) -> Path | None:
    """Save unseen content; return None for duplicates without modifying their files.

    Updated content at the same URL replaces that URL's file. Its old hash stays
    in the seen history. A single sequential crawler should own an output directory.
    """
    path = Path(output_dir) / url_filename(document["url"])
    record = ContentHashRecord(Path(output_dir))
    records = record.records()
    digest = content_hash(document["text"])
    if digest in records:
        record.persist(records)
        return None
    payload = {key: document[key] for key in ("url", "title", "text", "crawled_at")}
    payload["content_hash"] = digest
    if "blocks" in document:
        payload["blocks"] = document["blocks"]
    write_json_atomic(path, payload)
    records[digest] = document["url"]
    record.persist(records)
    return path
