import json
from pathlib import Path
import subprocess
import sys

import httpx
import pytest

from server.crawler import ContentHashRecord, content_hash, crawl_url, normalize_content, save_document, url_filename
from server.crawler import storage


def document(url="https://example.com/first", text="Hello world!"):
    return {"url": url, "title": "Title", "text": text, "crawled_at": "2026-01-01T00:00:00+00:00"}


def test_hash_determinism_and_meaningful_differences():
    assert content_hash("Hello world!") == content_hash("Hello world!")
    assert len(content_hash("Hello world!")) == 64
    for other in ("hello world!", "Hello world?", "world Hello!", "Hello worlds!"):
        assert content_hash(other) != content_hash("Hello world!")


@pytest.mark.parametrize("text", [" Hello  world! ", "Hello\r\nworld!", "Hello\rworld!",
                                  "\tHello\n\n  world!\t", "Hello\u00a0world!"])
def test_whitespace_variants(text):
    assert normalize_content(text) == "Hello world!"
    assert content_hash(text) == content_hash("Hello world!")


def test_new_content_duplicates_and_first_document_preserved(tmp_path):
    record = ContentHashRecord(tmp_path)
    assert not record.has_seen("Hello world!")
    first = save_document(document(), tmp_path)
    original = first.read_bytes()
    assert record.has_seen("Hello world!")
    assert save_document(document("https://example.com/second", "Hello\r\n world!"), tmp_path) is None
    assert first.read_bytes() == original
    assert not (tmp_path / url_filename("https://example.com/second")).exists()
    assert save_document(document(), tmp_path) is None
    assert save_document(document("https://example.com/third", "New content."), tmp_path)
    assert len(record.records()) == 2


def test_persistence_in_a_separate_python_process(tmp_path):
    save_document(document(), tmp_path)
    code = """
import sys
from pathlib import Path
from server.crawler import ContentHashRecord, save_document
directory = Path(sys.argv[1])
assert ContentHashRecord(directory).has_seen('Hello   world!')
assert save_document({'url': 'https://example.com/second', 'title': 'Other',
                      'text': 'Hello world!', 'crawled_at': 'now'}, directory) is None
"""
    subprocess.run([sys.executable, "-c", code, str(tmp_path)], check=True,
                   cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)
    assert not (tmp_path / url_filename("https://example.com/second")).exists()


def test_crawl_duplicate_status_and_preserved_extracted_text(tmp_path):
    def handler(request):
        return httpx.Response(200, headers={"Content-Type": "text/html"},
                              text='<title>Title</title><main><pre>if x:\n    print("hello")</pre></main>')
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        first = crawl_url("https://example.com/a", client=client, output_dir=tmp_path)
        second = crawl_url("https://example.com/b", client=client, output_dir=tmp_path)
        unsaved = crawl_url("https://example.com/c", client=client, output_dir=None)
    assert first["is_duplicate"] is False
    assert second["is_duplicate"] is True
    assert unsaved["is_duplicate"] is None
    assert first["text"] == 'if x:\n    print("hello")'
    assert first["content_hash"] == second["content_hash"]
    saved = json.loads((tmp_path / url_filename(first["url"])).read_text())
    assert saved["text"] == first["text"]
    assert saved["content_hash"] == content_hash(first["text"])
    assert "is_duplicate" not in saved


def test_legacy_documents_seed_record_without_modification(tmp_path):
    legacy = tmp_path / url_filename(document()["url"])
    legacy.write_text(json.dumps(document()), encoding="utf-8")
    original = legacy.read_bytes()
    assert save_document(document("https://example.com/copy"), tmp_path) is None
    assert legacy.read_bytes() == original
    assert (tmp_path / "content_hashes.json").exists()


def test_updated_url_retains_seen_history(tmp_path):
    save_document(document(), tmp_path)
    path = save_document(document(text="Changed content"), tmp_path)
    assert json.loads(path.read_text())["text"] == "Changed content"
    assert ContentHashRecord(tmp_path).has_seen("Hello world!")
    assert save_document(document("https://example.com/old-copy"), tmp_path) is None


def test_failed_document_write_does_not_record_hash(tmp_path, monkeypatch):
    def fail(*args):
        raise OSError("disk failure")
    monkeypatch.setattr(storage, "write_json_atomic", fail)
    with pytest.raises(OSError, match="disk failure"):
        save_document(document(), tmp_path)
    assert not ContentHashRecord(tmp_path).has_seen("Hello world!")


def test_record_failure_recovers_from_document(tmp_path, monkeypatch):
    with monkeypatch.context() as patch:
        patch.setattr(ContentHashRecord, "persist", lambda *args: (_ for _ in ()).throw(OSError("disk failure")))
        with pytest.raises(OSError):
            save_document(document(), tmp_path)
    assert ContentHashRecord(tmp_path).has_seen("Hello world!")
    assert save_document(document("https://example.com/retry"), tmp_path) is None


def test_corrupt_record_is_not_silently_reset(tmp_path):
    (tmp_path / "content_hashes.json").write_text("not json", encoding="utf-8")
    with pytest.raises(ValueError):
        save_document(document(), tmp_path)
    assert not (tmp_path / url_filename(document()["url"])).exists()
