"""Full existing retrieval -> context -> Gemini demo. Makes one real LLM call."""
import argparse
import json
from pathlib import Path
from time import perf_counter

from server.ai.providers.gemini import create_model
from server.ai.rag import build_context
from server.ai.rag.generator import RAGGenerator


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", default="What is SQL injection?")
    parser.add_argument("--top-k", type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.top_k <= 10:
        parser.error("--top-k must be between 1 and 10")
    # Fail fast on missing configuration before loading the retrieval models.
    model, name = create_model()
    from fastapi.testclient import TestClient
    from server.api import app
    start = perf_counter()
    with TestClient(app) as client:
        response = client.get("/api/search", params={"q": args.query, "top_k": 10})
        response.raise_for_status()
        context = build_context(args.query, response.json()["results"], top_k=args.top_k)
    print("Query:", args.query)
    print("Retrieved sources:", json.dumps([{"number": c.source_id, "title": c.title, "url": c.url}
        for c in context.chunks], indent=2))
    generation_start = perf_counter()
    result = RAGGenerator(model=model, provider="gemini", model_name=name,
                          max_chunks=args.top_k).generate(args.query, context)
    report = {"query": args.query, **result.model_dump(),
              "generation_seconds": perf_counter() - generation_start,
              "total_pipeline_seconds": perf_counter() - start}
    print(json.dumps(report, indent=2, ensure_ascii=False))
    output = Path(__file__).resolve().parent / "results/rag_generation_example.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
