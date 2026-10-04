"""Manual, read-only validation of a completed small crawl against Qdrant/API.

Uses real cached models and the configured Qdrant server. Not a unit test.
Run from the project root: python -m evaluation.validate_crawler
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import sqlite3

from fastapi.testclient import TestClient

from server import api
from server.crawler.dedup import content_hash, write_json_atomic
from server.crawler.indexing import DEFAULT_INDEX_FILE


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, default=Path("crawler_runs/validation-live"))
    parser.add_argument("--output", type=Path, default=Path("evaluation/crawler_validation.json"))
    parser.add_argument("--query-set", type=Path, help="JSON array of [query, source, expected_url]")
    args = parser.parse_args()
    manifest = json.loads(DEFAULT_INDEX_FILE.read_text(encoding="utf-8"))
    with sqlite3.connect(args.run_dir / "frontier.sqlite3") as frontier:
        rows = frontier.execute("SELECT normalized_url,document_path FROM urls WHERE indexed=1 AND attempts>0").fetchall()
    assert rows, "The run has no successfully indexed documents"
    expected, pages, chunks = {}, Counter(), Counter()
    bm25_names = {name for posting in manifest["bm25_index"].values() for name in posting}
    for url, path in rows:
        saved = json.loads(Path(path).read_text(encoding="utf-8"))
        indexed = manifest["documents"][url]
        assert saved["content_hash"] == content_hash(saved["text"])
        assert saved["blocks"] == indexed["blocks"]
        assert indexed["document_name"] in bm25_names
        pages[saved["domain"]] += 1
        for chunk in indexed["chunks"]:
            for key in ("source", "domain", "title", "content_hash", "crawled_at"):
                assert chunk[key] == saved[key], (url, key)
            expected[chunk["chunk_id"]] = chunk
            chunks[saved["domain"]] += 1
    queries = [
        ("How do CSS color-mix functions create color palettes?", "mdn",
         "https://developer.mozilla.org/en-US/blog/color-palettes-css-color-mix/"),
        ("Convert a min heap to a max heap", "gfg",
         "https://www.geeksforgeeks.org/dsa/convert-min-heap-to-max-heap/"),
        ("Broadcast Channel API communication between browser tabs", "mdn",
         "https://developer.mozilla.org/en-US/blog/exploring-the-broadcast-channel-api-for-cross-tab-communication/"),
        ("Find the smallest range containing elements from k sorted lists", "gfg",
         "https://www.geeksforgeeks.org/dsa/find-smallest-range-containing-elements-from-k-lists/"),
    ]
    if args.query_set:
        queries = json.loads(args.query_set.read_text(encoding="utf-8"))
    results = []
    with TestClient(api.app) as client:
        seen, samples = {}, {}
        offset = None
        while True:
            points, offset = api.state.client.scroll(api.state.collection, offset=offset,
                limit=256, with_payload=True, with_vectors=False)
            for point in points:
                payload = point.payload
                chunk = expected.get(payload.get("chunk_id"))
                if chunk is None:
                    continue
                assert payload["chunk_id"] not in seen, "Duplicate vector chunk"
                for key in ("document_name", "chunk_id", "text", "title", "source", "domain",
                            "content_hash", "crawled_at", "heading_path", "chunk_index", "token_count", "chunking_config"):
                    assert payload[key] == chunk[key], (payload["chunk_id"], key)
                assert payload["url"] == chunk["source_url"]
                seen[payload["chunk_id"]] = point.id
                samples.setdefault(payload["source"], point.id)
            if offset is None:
                break
        assert seen.keys() == expected.keys(), "Qdrant is missing indexed chunks"
        vectors = api.state.client.retrieve(api.state.collection, ids=list(samples.values()), with_vectors=True)
        assert all(len(point.vector) == 384 for point in vectors)
        for query, source, target in queries:
            response = client.get("/api/search", params={"q": query, "top_k": 10})
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["pipeline"] == "hybrid_rrf_reranker"
            hits = body["results"]
            matching = [(rank, hit) for rank, hit in enumerate(hits, 1) if hit["url"] == target]
            assert matching, f"Expected crawled page missing for {query}"
            assert matching[0][1]["source"] == source
            assert matching[0][1]["domain"]
            results.append({"query": query, "expected_url": target, "expected_rank": matching[0][0],
                            "results": [{k: hit[k] for k in ("title", "url", "source", "domain", "rrf_score", "reranker_score")} for hit in hits]})
        total_vectors = api.state.client.count(api.state.collection, exact=True).count
        corpus_size = client.get("/api/health").json()["documents"]
    report = {"pages_verified_by_domain": dict(pages), "chunks_verified_by_domain": dict(chunks),
              "total_new_chunks_verified": len(expected), "collection_total_vectors": total_vectors,
              "api_corpus_documents": corpus_size, "vector_dimensions": 384,
              "checks": ["saved content hashes", "structural blocks", "BM25 membership", "Qdrant chunk completeness and uniqueness",
                         "metadata equality", "vector dimensions", "real hybrid/RRF/cross-encoder API queries"],
              "queries": results}
    write_json_atomic(args.output, report)
    print(json.dumps({k: v for k, v in report.items() if k != "queries"}, indent=2))
    print(json.dumps([{k: v for k, v in q.items() if k != "results"} for q in results], indent=2))


if __name__ == "__main__":
    main()
