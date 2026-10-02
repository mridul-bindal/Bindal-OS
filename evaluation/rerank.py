"""Compare reranking against a frozen run of the existing retrieval evaluator."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from evaluation.evaluate import ROOT, METRICS, retrieval_metrics
from server.file_loader import load_files
from server.reranking import DEFAULT_MODEL, rerank


def compare(before, after):
    deltas = {key: after["metrics"][key] - before["metrics"][key] for key in METRICS}
    positive, negative = any(v > 0 for v in deltas.values()), any(v < 0 for v in deltas.values())
    changed = before["ranking"] != after["ranking"]
    category = ("mixed" if positive and negative else "improved" if positive else
                "decreased" if negative else "changed_without_metric_gain" if changed else "unchanged")
    return {"category": category, "ranking_changed": changed, "metric_deltas": deltas}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=ROOT / "evaluation/results/results.json")
    parser.add_argument("--queries", type=Path, default=ROOT / "evaluation/queries.json")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "evaluation/reranking_results")
    parser.add_argument("--candidate-k", type=int, default=10)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args()
    rerank("validate", [], candidate_k=args.candidate_k, top_k=args.top_k, model_name=args.model)
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    judgments = json.loads(args.queries.read_text(encoding="utf-8"))["queries"]
    if hashlib.sha256(args.queries.read_bytes()).hexdigest() != baseline["metadata"]["query_set_sha256"]:
        raise ValueError("Relevance judgments changed since the baseline run")
    documents = load_files(str(ROOT / "data"))
    hashes = {name: hashlib.sha256(text.encode()).hexdigest() for name, text in documents.items()}
    if hashes != baseline["metadata"]["document_sha256"]:
        raise ValueError("Corpus changed since the baseline run; regenerate baseline first")
    labels = {q["id"]: q for q in judgments}
    if {row["id"] for row in baseline["per_query"]} != set(labels):
        raise ValueError("Baseline does not cover the query set")
    rows = []
    for row in baseline["per_query"]:
        label = labels[row["id"]]
        if row["query"] != label["query"] or row["relevant_documents"] != label["relevant_documents"]:
            raise ValueError("Baseline query or labels disagree with the fixed judgments")
        results = rerank(row["query"], row["rrf_results"], candidate_k=args.candidate_k,
                         top_k=args.top_k, model_name=args.model,
                         document_metadata={name: {"text": text} for name, text in documents.items()})
        systems = {name: {"ranking": result["ranking"],
                           "metrics": retrieval_metrics(result["ranking"], set(label["relevant_documents"]))}
                   for name, result in row["systems"].items()}
        ranking = [r["document_name"] for r in results]
        systems["rrf_reranker"] = {"ranking": ranking,
                                   "metrics": retrieval_metrics(ranking, set(label["relevant_documents"]))}
        rows.append({**label, "systems": systems, "reranked_results": results,
                     "change": compare(systems["rrf"], systems["rrf_reranker"])})
        print(f"{row['id']}: {rows[-1]['change']['category']}", flush=True)
    systems = ("bm25", "semantic", "rrf", "rrf_reranker")
    aggregate = {s: {m: sum(r["systems"][s]["metrics"][m] for r in rows) / len(rows)
                     for m in METRICS} for s in systems}
    report = {"metadata": {"evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
              "model": args.model, "candidate_k": args.candidate_k, "top_k": args.top_k,
              "max_length": 512, "baseline_metadata": baseline["metadata"],
              "baseline_sha256": hashlib.sha256(args.baseline.read_bytes()).hexdigest()},
              "aggregate": aggregate, "per_query": rows}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "results.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = ["# Cross-encoder evaluation", "", f"Model: `{args.model}`; candidate_k={args.candidate_k}; top_k={args.top_k}; maximum input length=512 tokens.",
             "", "Frozen BM25, semantic and RRF outputs from the existing evaluation are reused. Corpus and manual relevance labels are checked against their original hashes. Metrics use only those labels, never model scores. No tuning was performed on the labels.",
             "", "Each candidate uses its best semantic chunk; missing chunk text falls back to full document text. Long pairs may be truncated by the cross-encoder. Score ties preserve RRF order.",
             "", "This development set contains 40 queries and only 10 documents, with repeated source paragraphs. Recall@10 has a ceiling effect. Changes in irrelevant-document order need not improve measured relevance. If top_k or candidate_k is below 10, Recall@10 measures only that truncated result set.",
             "", "## Aggregate metrics", "", "| Stage | Recall@5 | Recall@10 | MRR |", "|---|---:|---:|---:|"]
    for s in systems:
        lines.append(f"| {s} | " + " | ".join(f"{aggregate[s][m]:.4f}" for m in METRICS) + " |")
    lines += ["", "## Per-query metrics", "", "Cells show Recall@5 / Recall@10 / reciprocal rank. Full rankings, candidate metadata and reranker scores are in results.json.",
              "", "| ID | Query | BM25 | Semantic | RRF | RRF + reranker | Change |", "|---|---|---|---|---|---|---|"]
    for row in rows:
        cells = [" / ".join(f"{row['systems'][s]['metrics'][m]:.4f}" for m in METRICS) for s in systems]
        lines.append(f"| {row['id']} | {row['query']} | " + " | ".join(cells) + f" | {row['change']['category']} |")
    lines += ["", "## Changes relative to RRF", "", "Improved/decreased means at least one metric changes in that direction and none changes in the opposite direction. Mixed means both gains and losses. Changed without metric gain means a different ranking but identical measured relevance."]
    for category in ("improved", "changed_without_metric_gain", "decreased", "mixed", "unchanged"):
        selected = [r for r in rows if r["change"]["category"] == category]
        lines += ["", f"### {category} ({len(selected)})", ""]
        for row in selected:
            delta = ", ".join(f"{m}: {v:+.4f}" for m, v in row["change"]["metric_deltas"].items())
            lines.append(f"- {row['id']}: {row['query']} ({delta})")
        if not selected:
            lines.append("None.")
    (args.output_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(aggregate, indent=2))


if __name__ == "__main__":
    main()
