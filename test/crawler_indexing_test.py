from contextlib import closing
import json
from unittest.mock import Mock

import pytest
from qdrant_client import QdrantClient

from server.chunking import chunk_document
from server.crawler.chunking import chunk_crawled_document
from server.crawler.dedup import content_hash
from server.crawler.indexing import index_crawled_chunks
from server.search_engine.BM25 import build_bm25_index, search_bm25_index
from server.semantic_search.embeddings import embed_chunks
from server.semantic_search.vector_store import store_chunks


class Model:
    def encode(self, texts):
        return [[0.1] * 384 for text in texts]


def chunks(url="https://example.com/a", text="mongodb indexes improve queries efficiently"):
    return chunk_crawled_document({"url": url, "title": "MongoDB guide", "text": text,
                                  "content_hash": content_hash(text), "crawled_at": "2026-01-01T00:00:00+00:00"},
                                 chunk_words=3, overlap_words=1)


def save(client, tmp_path, page, **kwargs):
    return index_crawled_chunks(page, client=client, collection="chunks", index_file=tmp_path / "index.json",
                                chunk_words=3, overlap_words=1, model=Model(), **kwargs)


def test_shared_bm25_and_vector_indexers_preserve_metadata(tmp_path):
    page = chunks()
    with closing(QdrantClient(":memory:")) as client:
        result = save(client, tmp_path, page)
        assert result["bm25_index"] == build_bm25_index({page[0].document_name: "mongodb indexes improve queries efficiently"})
        assert search_bm25_index("indexes", result["bm25_index"])[0]["file_name"] == page[0].document_name
        points, _ = client.scroll("chunks", with_vectors=True)
        assert len(points) == len(page)
        for point in points:
            original = next(c for c in page if c.chunk_id == point.payload["chunk_id"])
            for key in ("document_name", "source_url", "title", "chunk_id", "text", "content_hash", "crawled_at"):
                assert point.payload[key] == getattr(original, key)
            assert len(point.vector) == 384
        assert json.loads((tmp_path / "index.json").read_text()) == result


def test_reindex_is_idempotent_and_replacement_removes_stale_chunks(tmp_path):
    with closing(QdrantClient(":memory:")) as client:
        original = chunks(text="obsolete old details about database indexes here today")
        save(client, tmp_path, original)
        ids = {p.id for p in client.scroll("chunks")[0]}
        save(client, tmp_path, original + original)
        assert {p.id for p in client.scroll("chunks")[0]} == ids
        other = chunks("https://example.com/b", "replication maintains availability")
        save(client, tmp_path, other)
        replacement = chunks(text="fresh replacement text")
        result = save(client, tmp_path, replacement)
        points, _ = client.scroll("chunks")
        assert len(points) == 2
        assert not ids & {p.id for p in points}
        assert {p.payload["document_name"] for p in points} == {replacement[0].document_name, other[0].document_name}
        assert "obsolete" not in result["bm25_index"]
        assert search_bm25_index("replication", result["bm25_index"])
        assert len(result["documents"]) == 2


def test_local_pipeline_and_crawler_sources_are_isolated(tmp_path):
    with closing(QdrantClient(":memory:")) as client:
        local = embed_chunks(chunk_document("local.txt", "local source text"), model=Model())
        assert local[0].metadata == {}
        store_chunks(client, "chunks", local, source="local-folder", chunk_words=250, overlap_words=40)
        save(client, tmp_path, chunks())
        store_chunks(client, "chunks", local, source="local-folder", chunk_words=250, overlap_words=40)
        save(client, tmp_path, chunks(text="updated webpage"))
        points, _ = client.scroll("chunks")
        local_point = next(p for p in points if p.payload["document_name"] == "local.txt")
        assert local_point.payload["text"] == "local source text"
        assert "source_url" not in local_point.payload
        assert len(points) == 2


def test_multiple_pages_and_changed_chunk_settings(tmp_path):
    with closing(QdrantClient(":memory:")) as client:
        page = chunks()
        result = save(client, tmp_path, page + chunks("https://example.com/b", "replication protects availability"))
        assert len(result["documents"]) == 2
        revised = chunk_crawled_document({"url": page[0].source_url, "title": page[0].title,
            "text": "mongodb indexes improve queries efficiently", "content_hash": page[0].content_hash},
            chunk_words=10, overlap_words=0)
        index_crawled_chunks(revised, client=client, collection="chunks", index_file=tmp_path / "index.json",
                             chunk_words=10, overlap_words=0, model=Model())
        assert client.count("chunks").count == 2


def test_incomplete_chunks_rejected_before_index_mutation(tmp_path):
    client = Mock()
    with pytest.raises(ValueError, match="Incomplete"):
        save(client, tmp_path, chunks()[:1])
    assert not client.mock_calls
    assert not (tmp_path / "index.json").exists()


def test_failure_keeps_previous_bm25_manifest_and_retry_recovers(tmp_path, monkeypatch):
    with closing(QdrantClient(":memory:")) as client:
        page = chunks()
        save(client, tmp_path, page)
        before = (tmp_path / "index.json").read_bytes()
        with monkeypatch.context() as patch:
            def fail(**kwargs):
                raise RuntimeError("upload failed")
            patch.setattr(client, "upsert", fail)
            with pytest.raises(RuntimeError, match="upload failed"):
                save(client, tmp_path, chunks(text="new text"))
        assert (tmp_path / "index.json").read_bytes() == before
        assert client.count("chunks").count == len(page)
        save(client, tmp_path, chunks(text="new text"))
        assert client.count("chunks").count == 1


def test_empty_batch_is_a_noop(tmp_path):
    client = Mock()
    assert save(client, tmp_path, []) == {"documents": {}, "bm25_index": {}}
    assert not client.mock_calls
    assert not (tmp_path / "index.json").exists()
