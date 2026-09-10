"""FastAPI backend for Bindal Sach Engine (BM25 document search)."""
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from server import load_files
from server.search_engine import (
    build_bm25_index,
    remove_stopwords,
    search_bm25_index_with_snippets,
)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


class SearchHit(BaseModel):
    file_name: str
    score: float
    snippet: list[str] = Field(default_factory=list)


class SearchResponse(BaseModel):
    query: str
    cleaned_query: str
    count: int
    results: list[SearchHit]


class EngineState:
    file_data: dict[str, str] = {}
    bm25_index: dict[str, dict[str, float]] = {}


state = EngineState()


def _load_engine() -> None:
    if not DATA_DIR.is_dir():
        raise RuntimeError(f"Data directory not found: {DATA_DIR}")
    file_data = load_files(str(DATA_DIR))
    if not file_data:
        raise RuntimeError(f"No .txt documents found in {DATA_DIR}")
    state.file_data = file_data
    state.bm25_index = build_bm25_index(file_data)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _load_engine()
    yield


app = FastAPI(
    title="Bindal Sach Engine",
    description="BM25 document search API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "engine": "Bindal Sach Engine",
        "documents": len(state.file_data),
        "indexed_terms": len(state.bm25_index),
    }


@app.get("/api/search", response_model=SearchResponse)
def search(
    q: str = Query(..., min_length=1, description="Search query"),
) -> SearchResponse:
    query = q.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query must not be empty")

    if not state.bm25_index:
        raise HTTPException(status_code=503, detail="Search index is not ready")

    cleaned_query = remove_stopwords(query)
    raw_results = search_bm25_index_with_snippets(
        cleaned_query or query,
        state.bm25_index,
        state.file_data,
    )
    results = [
        SearchHit(
            file_name=str(item["file_name"]),
            score=float(item["score"]),
            snippet=list(item.get("snippet") or []),
        )
        for item in raw_results
    ]
    return SearchResponse(
        query=query,
        cleaned_query=cleaned_query,
        count=len(results),
        results=results,
    )
