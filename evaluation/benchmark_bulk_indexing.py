ew whats h"""Manual same-data benchmark: refresh 25 existing pages, without crawling new URLs."""
from collections import Counter
import json
from pathlib import Path
import time

from server.crawler.chunking import chunk_crawled_documents
from server.crawler.dedup import write_json_atomic
from server.crawler.indexing import DEFAULT_INDEX_FILE
from server.crawler.storage import DEFAULT_OUTPUT_DIR, url_filename
from server.semantic_search.embeddings import embed_chunks, get_embedding_model
from server.semantic_search.vector_store import connect_qdrant, store_chunks, store_chunk_groups


def main():
    manifest = json.loads(DEFAULT_INDEX_FILE.read_text(encoding="utf-8"))
    selected = [(url, doc) for url, doc in manifest["documents"].items() if doc.get("source")][:25]
    pages = {}
    for url, doc in selected:
        saved = json.loads((DEFAULT_OUTPUT_DIR / url_filename(url)).read_text(encoding="utf-8"))
        chunks = chunk_crawled_documents([saved])
        assert [(c.chunk_id, c.text) for c in chunks] == [(c["chunk_id"], c["text"]) for c in doc["chunks"]]
        pages[f"crawler:{url}"] = chunks
    model = get_embedding_model()
    embed_chunks(next(iter(pages.values())), model=model)
    client, collection = connect_qdrant()
    calls = Counter()
    for name in ("collection_exists", "get_collection", "create_payload_index", "upsert", "delete"):
        original = getattr(client, name)
        def tracked(*args, _name=name, _original=original, **kwargs):
            calls[_name] += 1
            return _original(*args, **kwargs)
        setattr(client, name, tracked)
    try:
        before = client.count(collection, exact=True).count
        started = time.perf_counter()
        for scope, page in pages.items():
            store_chunks(client, collection, embed_chunks(page, model=model), source=scope, overlap_words=40)
        serial_seconds = time.perf_counter() - started
        serial_calls = dict(calls)
        calls.clear()
        started = time.perf_counter()
        embedded = embed_chunks([c for page in pages.values() for c in page], model=model)
        groups, offset = {}, 0
        for scope, page in pages.items():
            groups[scope] = embedded[offset:offset + len(page)]
            offset += len(page)
        store_chunk_groups(client, collection, groups, overlap_words=40)
        bulk_seconds = time.perf_counter() - started
        after = client.count(collection, exact=True).count
        assert before == after
        result = {"documents": len(pages), "chunks": len(embedded), "points_before": before,
                  "points_after": after, "serial_seconds": serial_seconds, "bulk_seconds": bulk_seconds,
                  "speedup": serial_seconds / bulk_seconds, "serial_calls": serial_calls, "bulk_calls": dict(calls),
                  "scope": "Same saved documents, warm MiniLM; embedding and Qdrant operations only. No crawling or BM25 rebuild."}
        write_json_atomic(Path("evaluation/bulk_indexing_benchmark.json"), result)
        print(json.dumps(result, indent=2))
    finally:
        client.close()


if __name__ == "__main__":
    main()
