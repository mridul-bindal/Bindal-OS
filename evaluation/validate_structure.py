"""Explicit live migration/validation of local corpus and a supplied webpage."""
import argparse
import json
from pathlib import Path

from evaluation.evaluate import ROOT, retrieval_metrics
from server.file_loader import load_files
from server.search_engine.BM25 import build_bm25_index, search_bm25_index
from server.search_engine.indexing import build_inverted_index, build_ranked_inverted_index
from server.search_engine.calculate_idf import build_tfidf_index
from server.search_engine.saveIndex import save_index
from server.search_engine.tokenizer import TOKENIZATION_VERSION, tokenize
from server.semantic_search.build_embeddings import build_embedding_database
from server.semantic_search.structured_chunking import get_token_counter
from server.semantic_search.vector_store import connect_qdrant
from server.crawler import crawl_url
from server.crawler.chunking import chunk_crawled_document
from server.crawler.indexing import index_crawled_chunks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    args = parser.parse_args()
    files = load_files(str(ROOT / "data"))
    bm25 = build_bm25_index(files)
    for filename, index in (("bm25_index.json", bm25), ("inverted_index.json", build_inverted_index(files)),
                            ("ranked_inverted_index.json", build_ranked_inverted_index(files)),
                            ("tfidf_index.json", build_tfidf_index(files))):
        save_index(index, ROOT / "data" / filename, overwrite=True)
    print("Rebuilt local lexical indexes", flush=True)
    count = build_embedding_database(ROOT / "data")
    print(f"Reindexed {count} local token-aware chunks", flush=True)
    doc = crawl_url(args.url)
    # Explicit re-indexing of an already-saved page is allowed. This does not
    # alter crawler deduplication or save a second document.
    source = {key: value for key, value in doc.items() if key != "is_duplicate"}
    chunks = chunk_crawled_document(source)
    counter = get_token_counter()
    assert all(counter.count(c.text) <= counter.model_limit for c in chunks)
    client, collection = connect_qdrant()
    try:
        indexed = index_crawled_chunks(chunks, client=client, collection=collection)
        total = client.count(collection, exact=True).count
        index_crawled_chunks(chunks, client=client, collection=collection)
        assert client.count(collection, exact=True).count == total
        points, offset = [], None
        while True:
            batch, offset = client.scroll(collection, limit=100, offset=offset, with_payload=True)
            points.extend(batch)
            if offset is None:
                break
        assert all(counter.count(p.payload["text"]) <= counter.model_limit for p in points)
        assert sum(p.payload.get("source_url") == args.url for p in points) == len(chunks)
    finally:
        client.close()
    variants = ("MongoDB", "mongo DB", "mongodb")
    local_results = {q: search_bm25_index(q, bm25) for q in variants}
    crawler_results = {q: search_bm25_index(q, indexed["bm25_index"]) for q in variants}
    local_sets = [set(r["file_name"] for r in results) for results in local_results.values()]
    assert local_sets[0] == local_sets[1] == local_sets[2]
    pairs = [("RedisCache", "redis cache"), ("VectorStore", "vector store"),
             ("Node.js", "node js"), ("React.js", "react js"),
             ("machine-learning", "machine learning"), ("shard-key", "shard key")]
    generalization = []
    for a, b in pairs:
        index = build_bm25_index({"target": a, "other": "elephant habitat"})
        forward = search_bm25_index(b, index)
        reverse = search_bm25_index(a, build_bm25_index({"target": b, "other": "elephant habitat"}))
        assert forward[0]["file_name"] == reverse[0]["file_name"] == "target"
        generalization.append({"forms": [a, b], "forward": forward, "reverse": reverse})
    judgments = json.loads((ROOT / "evaluation/queries.json").read_text(encoding="utf-8"))["queries"]
    metrics = [retrieval_metrics([r["file_name"] for r in search_bm25_index(q["query"], bm25)],
                                 set(q["relevant_documents"])) for q in judgments]
    aggregate = {key: sum(m[key] for m in metrics) / len(metrics) for key in metrics[0]}
    report = {"tokenization_version": TOKENIZATION_VERSION, "local_chunk_count": count,
        "crawler_chunk_count": len(chunks), "collection_points": total,
        "requested_max_tokens": 300, "effective_max_tokens": counter.model_limit,
        "max_observed_tokens": max(counter.count(p.payload["text"]) for p in points),
        "url": args.url, "title": doc["title"], "characters": len(doc["text"]),
        "block_counts": {kind: sum(b["kind"] == kind for b in doc["blocks"]) for kind in {b["kind"] for b in doc["blocks"]}},
        "heading_paths": [list(c.heading_path) for c in chunks],
        "local_bm25_variants": local_results, "crawler_bm25_variants": crawler_results,
        "generalization": generalization, "bm25_40_query_metrics": aggregate,
        "reindex_idempotent": True, "all_stored_vectors_within_model_limit": True}
    destination = ROOT / "evaluation/structure_validation.json"
    destination.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key not in {
        "heading_paths", "local_bm25_variants", "crawler_bm25_variants", "generalization"}}, indent=2))


if __name__ == "__main__":
    main()
