"""Read-only live retrieval demo; no answer generation or index writes."""
import argparse
import json
from pathlib import Path

import httpx

from server.ai.rag import build_context


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", default="What is SQL injection?")
    parser.add_argument("--top-k", type=int, default=2)
    parser.add_argument("--in-process", action="store_true",
                        help="Load the existing API lifecycle locally instead of connecting to a running server")
    args = parser.parse_args()
    if not 1 <= args.top_k <= 10:
        parser.error("--top-k must be between 1 and 10")
    params = {"q": args.query, "top_k": 10}
    if args.in_process:
        from fastapi.testclient import TestClient
        from server.api import app
        with TestClient(app) as client:
            response = client.get("/api/search", params=params)
    else:
        response = httpx.get("http://127.0.0.1:8000/api/search", params=params, timeout=180)
    response.raise_for_status()
    context = build_context(args.query, response.json()["results"], top_k=args.top_k)
    output = Path(__file__).resolve().parent / "results"
    output.mkdir(parents=True, exist_ok=True)
    (output / "rag_context_example.json").write_text(
        json.dumps(context.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "rag_context_example.txt").write_text(context.format_context() + "\n", encoding="utf-8")
    print(context.format_context())


if __name__ == "__main__":
    main()
