"""Evaluate BM25, MiniLM and unweighted RRF against fixed manual judgments."""
import argparse
import csv
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from server.file_loader import load_files
from server.hybrid_search import aggregate_semantic_results, reciprocal_rank_fusion
from server.search_engine.BM25 import build_bm25_index, search_bm25_index
from server.semantic_search.embeddings import MODEL_NAME
from server.semantic_search.search import semantic_search
from server.semantic_search.vector_store import connect_qdrant

ROOT = Path(__file__).resolve().parents[1]
METRICS = ("recall_at_5", "recall_at_10", "reciprocal_rank")
SYSTEMS = ("bm25", "semantic", "rrf")


def retrieval_metrics(ranked_documents: list[str], relevant: set[str]) -> dict[str, float]:
    """Binary recall at document cutoffs and untruncated reciprocal rank."""
    if not relevant:
        raise ValueError("Each evaluation query needs at least one relevant document")
    ranked = list(dict.fromkeys(ranked_documents))
    return {
        "recall_at_5": len(set(ranked[:5]) & relevant) / len(relevant),
        "recall_at_10": len(set(ranked[:10]) & relevant) / len(relevant),
        "reciprocal_rank": next((1 / rank for rank, name in enumerate(ranked, 1)
                                  if name in relevant), 0.0),
    }


def aggregate(rows):
    return {system: {metric: sum(row["systems"][system]["metrics"][metric] for row in rows) / len(rows)
                     for metric in METRICS} for system in SYSTEMS}


def validate_snapshot(client, collection, documents):
    """Ensure the cloud candidates belong to the same local corpus as BM25."""
    offset = None
    points = []
    while True:
        batch, offset = client.scroll(collection, limit=100, offset=offset, with_payload=True)
        points.extend(batch)
        if offset is None:
            break
    names = set()
    for point in points:
        payload = point.payload or {}
        name, text = payload.get("document_name"), payload.get("text")
        if name not in documents or not text or text not in documents[name] or payload.get("model") != MODEL_NAME:
            raise ValueError("Qdrant collection does not match the local evaluation corpus/model")
        names.add(name)
    if names != set(documents):
        raise ValueError("Qdrant does not cover all local documents")
    snapshot = sorted((str(p.id), p.payload) for p in points)
    fingerprint = hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()
    return len(points), fingerprint


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--k", type=float, default=60)
    parser.add_argument("--queries", type=Path, default=ROOT / "evaluation/queries.json")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "evaluation/results")
    args = parser.parse_args()
    reciprocal_rank_fusion([], [], k=args.k)  # Validate before connecting.
    judgments = json.loads(args.queries.read_text(encoding="utf-8"))
    queries = judgments["queries"]
    documents = load_files(str(ROOT / "data"))
    if not queries or len({q["id"] for q in queries}) != len(queries):
        raise ValueError("Queries must have unique IDs and be non-empty")
    for query in queries:
        if not query["relevant_documents"] or not set(query["relevant_documents"]) <= documents.keys():
            raise ValueError(f"Invalid relevance labels for {query['id']}")
    index = build_bm25_index(documents)
    client, collection = connect_qdrant()
    rows = []
    try:
        count, snapshot_hash = validate_snapshot(client, collection, documents)
        for query in queries:
            bm25 = search_bm25_index(query["query"], index)
            # Full candidate depth avoids truncation bias from repeated chunks.
            chunks = semantic_search(query["query"], client=client, collection=collection, top_k=count)
            if len(chunks) != count:
                raise ValueError("Collection changed during evaluation")
            semantic = aggregate_semantic_results(chunks)
            hybrid = reciprocal_rank_fusion(bm25, chunks, k=args.k)
            rankings = {
                "bm25": [r["file_name"] for r in bm25],
                "semantic": [r.document_name for r in semantic],
                "rrf": [r.document_name for r in hybrid],
            }
            rows.append({**query, "systems": {
                system: {"ranking": ranking, "metrics": retrieval_metrics(ranking, set(query["relevant_documents"]))}
                for system, ranking in rankings.items()
            }, "rrf_results": [asdict(r) for r in hybrid]})
            print(f"Evaluated {query['id']}: {query['query']}", flush=True)
        if validate_snapshot(client, collection, documents) != (count, snapshot_hash):
            raise ValueError("Collection changed during evaluation; rerun for a consistent snapshot")
    finally:
        client.close()
    report = {
        "metadata": {
            "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
            "query_count": len(queries), "document_count": len(documents),
            "chunk_count": count, "collection": collection, "model": MODEL_NAME, "rrf_k": args.k,
            "candidate_depth": "All BM25 matches; all Qdrant chunks, then document deduplication",
            "query_set_sha256": hashlib.sha256(args.queries.read_bytes()).hexdigest(),
            "qdrant_payload_snapshot_sha256": snapshot_hash,
            "document_sha256": {name: hashlib.sha256(text.encode()).hexdigest() for name, text in documents.items()},
            "labeling": judgments["labeling"],
        },
        "aggregate": aggregate(rows),
        "by_category": {category: aggregate([r for r in rows if r["category"] == category])
                        for category in sorted({r["category"] for r in rows})},
        "per_query": rows,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "results.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    with (args.output_dir / "per_query.csv").open("w", newline="", encoding="utf-8") as output:
        writer = csv.writer(output)
        writer.writerow(["id", "category", "query", "relevant_documents", "system", *METRICS, "ranking"])
        for row in rows:
            for system, result in row["systems"].items():
                writer.writerow([row["id"], row["category"], row["query"], ";".join(row["relevant_documents"]),
                                 system, *[result["metrics"][m] for m in METRICS], ";".join(result["ranking"])])
    lines = ["# Retrieval evaluation", "", f"{len(rows)} manually labeled queries; {len(documents)} documents; {count} chunks; RRF k={args.k:g}.",
             "", "Labels were authored from document contents before this run, independently of retriever outputs.",
             "Recall@N is relevant documents in the first N unique results divided by all labeled relevant documents. MRR is mean reciprocal rank of the first relevant document (zero if absent). Aggregates are macro averages across queries.",
             "", "All available candidates are evaluated. Semantic document order uses the best-ranked chunk, with consecutive ranks after deduplication. RRF ties use document name. No parameter tuning was performed.",
             "", "Limitations: this is a small, manually judged development set, not an independently judged held-out benchmark. The source documents contain repeated paragraphs. With only ten documents and full candidate depth, Recall@10 is largely a coverage check. Results do not establish performance on larger corpora or shallow candidate pools.",
             "", "## Aggregate metrics", "", "| System | Recall@5 | Recall@10 | MRR |", "|---|---:|---:|---:|"]
    for system, scores in report["aggregate"].items():
        lines.append(f"| {system} | " + " | ".join(f"{scores[m]:.4f}" for m in METRICS) + " |")
    lines += ["", "## Metrics by query category", "", "| Category | System | Recall@5 | Recall@10 | MRR |", "|---|---|---:|---:|---:|"]
    for category, systems in report["by_category"].items():
        for system, scores in systems.items():
            lines.append(f"| {category} | {system} | " + " | ".join(f"{scores[m]:.4f}" for m in METRICS) + " |")
    lines += ["", "## Per-query results", "", "Each cell is Recall@5 / Recall@10 / reciprocal rank. Full rankings and chunk metadata are in results.json; tabular results are in per_query.csv.",
              "", "| ID | Query | Relevant documents | BM25 | Semantic | RRF |", "|---|---|---|---|---|---|"]
    for row in rows:
        cells = [" / ".join(f"{row['systems'][s]['metrics'][m]:.4f}" for m in METRICS) for s in SYSTEMS]
        lines.append(f"| {row['id']} | {row['query']} | {', '.join(row['relevant_documents'])} | " + " | ".join(cells) + " |")
    (args.output_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(report["aggregate"], indent=2))


if __name__ == "__main__":
    main()
