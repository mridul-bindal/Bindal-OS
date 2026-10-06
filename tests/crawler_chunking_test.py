from copy import deepcopy
from unittest.mock import patch

import httpx
import pytest

from server.chunking import DocumentChunk, chunk_document
from server.crawler import content_hash, crawl_url
from server.crawler.chunking import chunk_crawled_document, chunk_crawled_documents


def doc(url="https://example.com/a", text="one two three four five"):
    return {"url": url, "title": "A title", "text": text,
            "content_hash": content_hash(text), "crawled_at": "2026-01-01T00:00:00+00:00",
            "is_duplicate": False}


def test_single_document_reuses_chunker_and_preserves_metadata():
    document = doc(text="one  two\nthree four five")
    original = deepcopy(document)
    chunks = chunk_crawled_document(document, chunk_words=3, overlap_words=1)
    assert [c.text for c in chunks] == ["one  two\nthree", "three four five"]
    expected = chunk_document(chunks[0].document_name, document["text"], chunk_words=3, overlap_words=1)
    assert [(c.chunk_id, c.text) for c in chunks] == [(c.chunk_id, c.text) for c in expected]
    for c in chunks:
        assert isinstance(c, DocumentChunk)
        assert c.source_url == document["url"]
        assert c.title == document["title"]
        assert c.content_hash == document["content_hash"]
        assert c.crawled_at == document["crawled_at"]
    assert document == original


def test_multiple_documents_and_revisions_have_unique_stable_ids():
    documents = [doc(), doc("https://example.com/b", "six seven eight nine ten"),
                 doc(text="a new revision with words")]
    chunks = chunk_crawled_documents(iter(documents), chunk_words=3, overlap_words=1)
    assert len(chunks) == 6
    assert len({c.chunk_id for c in chunks}) == 6
    assert len({c.document_name for c in chunks}) == 3
    assert chunks == chunk_crawled_documents(documents, chunk_words=3, overlap_words=1)


def test_duplicates_never_reach_existing_chunker():
    first = doc()
    flagged = {**doc(text="different but flagged"), "is_duplicate": True}
    repeated = doc("https://example.com/mirror", "one\n two three four   five")
    with patch("server.crawler.chunking.chunk_document", wraps=chunk_document) as chunker:
        chunks = chunk_crawled_documents([flagged, first, repeated, first])
    assert chunker.call_count == 1
    assert len(chunks) == 1
    assert chunks[0].source_url == first["url"]


@pytest.mark.parametrize("documents", [[], [{}], [doc(text="")], [doc(text=" \n\t ")]])
def test_empty_documents_do_not_reach_chunker(documents):
    with patch("server.crawler.chunking.chunk_document") as chunker:
        assert chunk_crawled_documents(documents) == []
    chunker.assert_not_called()


def test_default_configuration():
    chunks = chunk_crawled_document(doc(text=" ".join(f"word{i}" for i in range(500))))
    assert len(chunks) >= 3
    assert all(c.token_count <= 256 for c in chunks)
    assert chunks[0].chunking_config["target_chunk_tokens"] == 200


@pytest.mark.parametrize("words,overlap", [(0, 0), (3, 3), (3, -1)])
def test_invalid_configuration(words, overlap):
    with pytest.raises(ValueError):
        chunk_crawled_document(doc(), chunk_words=words, overlap_words=overlap)


def test_saved_and_legacy_documents_are_accepted():
    document = doc()
    del document["is_duplicate"]
    assert len(chunk_crawled_document(document)) == 1
    del document["content_hash"]
    assert chunk_crawled_document(document)[0].content_hash == content_hash(document["text"])


def test_mismatched_hash_is_rejected():
    with pytest.raises(ValueError, match="content_hash"):
        chunk_crawled_document({**doc(), "content_hash": "incorrect"})


def test_mocked_crawler_to_chunks_with_persistent_deduplication(tmp_path):
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(
        200, headers={"Content-Type": "text/html"}, text="<title>Page</title><main>one two three four five</main>"
    ))) as client:
        first = crawl_url("https://example.com/first", client=client, output_dir=tmp_path)
        duplicate = crawl_url("https://example.com/copy", client=client, output_dir=tmp_path)
    chunks = chunk_crawled_documents([first, duplicate], chunk_words=3, overlap_words=1)
    assert len(chunks) == 2
    assert all(c.source_url == first["url"] and c.title == "Page" for c in chunks)
