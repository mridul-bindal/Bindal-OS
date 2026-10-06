# Bindal-OS

Document search using BM25, MiniLM/Qdrant retrieval, reciprocal rank fusion and
cross-encoder reranking, with a controlled webpage ingestion pipeline.

## Project layout

```text
frontend/       React/Vite web application
server/         FastAPI backend, retrieval, indexing and crawler packages
scripts/        Console search comparison (used by main.py)
tests/          Deterministic automated tests
evaluation/     Evaluation tools, relevance judgments and recorded reports
docs/           Project notes and diagrams
data/           Local source documents and ignored runtime storage
  indexes/      Generated local-document indexes
  crawler/
    documents/  Saved webpages and content-hash history
    index/      Shared crawler BM25/metadata manifest
    runs/       Persistent frontiers and batch reports
.cache/         Ignored development/test caches
```

`server/paths.py` defines runtime defaults relative to the repository. Keep the
entire `data/crawler/` directory when backing up or moving an installation.
Qdrant credentials remain in `server/semantic_search/.env` (never commit them).
The Python environment stays in `.venv/`; frontend dependencies stay in
`frontend/node_modules/`.

## Run locally

From this directory:

```powershell
uv sync
uv run uvicorn server.api:app --reload --port 8000
```

In another terminal:

```powershell
cd frontend
npm ci
npm run dev
```

Open http://localhost:5173. API documentation is at http://localhost:8000/docs.
Restart the backend after adding documents to refresh its in-memory corpus.

## Tests and build

```powershell
uv run python -m pytest -q
npm --prefix frontend run build
```

`uv run python main.py` runs the console comparison. Crawler commands continue
to use `python -m server.crawler.multipage`; run directories now live beneath
`data/crawler/runs/`. See [crawler instructions](server/crawler/README.md) for
limits, resume and recovery options. See [layout migration](docs/layout.md) for
the old-to-new paths.
