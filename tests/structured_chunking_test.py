from contextlib import closing
import re
from unittest.mock import Mock

import pytest
from qdrant_client import QdrantClient

from server.crawler.extract import extract_structured_content
from server.crawler.chunking import chunk_crawled_document
from server.crawler.indexing import index_crawled_chunks
from server.crawler.dedup import content_hash
from server.semantic_search.chunking import chunk_document
from server.semantic_search.embeddings import embed_chunks
from server.search_engine.BM25 import build_bm25_index


def document(html):
    title, text, blocks = extract_structured_content(html)
    return dict(url="https://example.com/page", title=title, text=text, blocks=blocks,
                content_hash=content_hash(text), crawled_at="2026-10-02T00:00:00+00:00")


def test_dom_sections_heading_context_and_no_cross_section_overlap():
    doc = document('<main><h1>Database</h1><h2>Replication</h2><p>Copies stay available.</p>'
                   '<h3>Elections</h3><p>Choose a leader.</p><h2>Sharding</h2><p>Divide the data.</p></main>')
    chunks = chunk_crawled_document(doc)
    assert len(chunks) == 3
    assert chunks[0].heading_path == ("Database", "Replication")
    assert chunks[1].heading_path == ("Database", "Replication", "Elections")
    assert chunks[2].heading_path == ("Database", "Sharding")
    assert "Copies" not in chunks[1].text and "Elections" not in chunks[2].text
    for i, chunk in enumerate(chunks):
        assert chunk.chunk_index == i and chunk.text.startswith("Database")
        assert chunk.url == doc["url"] and chunk.title == doc["title"]
        assert chunk.content_hash == doc["content_hash"]
        assert chunk.crawled_at == doc["crawled_at"]
    assert len({c.chunk_id for c in chunks}) == 3


def test_lists_code_and_section_under_max_stay_together_even_above_target():
    doc = document('<main><h2>Example</h2><p>Intro text.</p><ul><li>First item</li><li>Second item</li></ul>'
                   '<pre>if ready:\n    run("a  b")</pre></main>')
    assert [b["kind"] for b in doc["blocks"]] == ["heading", "paragraph", "list", "code"]
    chunks = chunk_crawled_document(doc, target_chunk_tokens=8, max_chunk_tokens=30, overlap_tokens=2)
    assert len(chunks) == 1
    assert 'if ready:\n    run("a  b")' in chunks[0].text
    assert "First item\nSecond item" in chunks[0].text


def test_paragraph_boundaries_and_code_not_split_when_it_fits():
    code = 'if ready:\n    do_work()\n    finish()'
    doc = document('<main><h2>Steps</h2><p>' + 'word ' * 12 + '</p><pre>' + code + '</pre><p>' + 'other ' * 12 + '</p></main>')
    chunks = chunk_crawled_document(doc, target_chunk_tokens=12, max_chunk_tokens=20, overlap_tokens=2)
    assert len(chunks) > 1
    assert any(code in c.text for c in chunks)
    assert all(c.token_count <= 20 for c in chunks)


@pytest.mark.parametrize("kind", ["paragraph", "code", "list"])
def test_oversized_blocks_cover_all_content_with_limited_overlap(kind):
    text = " ".join(f"token{i}" for i in range(90))
    chunks = chunk_document("d", text, blocks=[{"kind": kind, "text": text}],
                            target_chunk_tokens=16, max_chunk_tokens=20, overlap_tokens=3)
    assert len(chunks) > 1
    assert all(c.token_count <= 20 for c in chunks)
    assert set(text.split()) == set(" ".join(c.text for c in chunks).split())
    assert len(set(chunks[0].text.split()) & set(chunks[1].text.split())) <= 3
    no_overlap = chunk_document("d", text, target_chunk_tokens=16, max_chunk_tokens=20, overlap_tokens=0)
    assert len(" ".join(c.text for c in no_overlap).split()) == 90


def test_token_limit_uses_model_cap_and_includes_heading_special_tokens():
    doc = document('<main><h1>Context title</h1><p>' + 'word ' * 600 + '</p></main>')
    chunks = chunk_crawled_document(doc)
    assert all(c.token_count <= 256 for c in chunks)
    assert all(c.chunking_config["effective_max_tokens"] == 256 for c in chunks)


def test_long_heading_and_oversized_code_terminate_without_losing_metadata():
    heading = " ".join(f"heading{i}" for i in range(100))
    doc = document(f'<main><h1>{heading}</h1><pre>' + '\n'.join(f'call{i}()' for i in range(100)) + '</pre></main>')
    chunks = chunk_crawled_document(doc, target_chunk_tokens=20, max_chunk_tokens=30, overlap_tokens=2)
    assert all(c.heading_path == (heading,) and c.token_count <= 30 for c in chunks)
    assert "call99()" in chunks[-1].text


def test_plain_text_does_not_invent_headings():
    chunks = chunk_document("d", "Heading-like text\n\nA paragraph.")
    assert chunks[0].heading_path == ()


def test_structure_and_original_text_go_through_indexing_without_duplicating_bm25(tmp_path):
    doc = document('<main><h1>MongoDB</h1><p>' + 'replication available ' * 50 + '</p></main>')
    chunks = chunk_crawled_document(doc, target_chunk_tokens=20, max_chunk_tokens=30, overlap_tokens=4)
    model = Mock(encode=lambda texts: [[.1] * 384 for _ in texts], spec=["encode"])
    with closing(QdrantClient(":memory:")) as client:
        result = index_crawled_chunks(chunks, client=client, index_file=tmp_path / "index.json", model=model)
        assert result["bm25_index"] == build_bm25_index({chunks[0].document_name: doc["text"]})
        points, _ = client.scroll("bindal_document_chunks", limit=100)
        assert len(points) == len(chunks)
        assert all(p.payload["heading_path"] == ["MongoDB"] for p in points)
        assert all(p.payload["url"] == doc["url"] for p in points)
        with pytest.raises(ValueError, match="Incomplete"):
            index_crawled_chunks(chunks[:-1], client=client, index_file=tmp_path / "index.json", model=model)


def test_embedding_refuses_silent_truncation():
    tokenizer = Mock(encode=lambda *a, **kw: list(range(300)))
    model = Mock(tokenizer=tokenizer, max_seq_length=256)
    with pytest.raises(ValueError, match="input limit"):
        embed_chunks(chunk_document("d", "small text"), model=model)
    model.encode.assert_not_called()


@pytest.mark.parametrize("options", [{"target_chunk_tokens": 0}, {"overlap_tokens": -1},
                                      {"target_chunk_tokens": 20, "max_chunk_tokens": 10},
                                      {"overlap_tokens": 200}])
def test_bad_token_configuration(options):
    with pytest.raises(ValueError):
        chunk_document("d", "text", **options)


def test_article_body_preferred_over_navigation():
    doc = document('<body><div>unrelated links</div><div itemprop="articleBody"><h1>Real</h1><p>Useful prose.</p></div></body>')
    assert "unrelated" not in doc["text"]
