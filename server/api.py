"""FastAPI backend for hybrid retrieval and cross-encoder reranking."""
import logging
from functools import lru_cache
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
)
from server.hybrid_search.service import hybrid_search, load_crawler_documents
from server.semantic_search.vector_store import connect_qdrant
from server.ai.rag import build_context
from server.ai.rag.generator import RAGGenerator, GenerationResponse, GenerationError
from server.ai.providers.gemini import ConfigurationError

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


class SearchHit(BaseModel):
    file_name: str
    score: float
    snippet: list[str] = Field(default_factory=list)
    title: str | None = None
    url: str | None = None
    source: str | None = None
    domain: str | None = None
    chunk_id: str | None = None
    text: str
    bm25_score: float | None = None
    semantic_score: float | None = None
    rrf_score: float
    reranker_score: float


class SearchResponse(BaseModel):
    query: str
    cleaned_query: str
    count: int
    results: list[SearchHit]
    pipeline: str = "hybrid_rrf_reranker"


class EngineState:
    file_data: dict[str, str] = {}
    bm25_index: dict[str, dict[str, float]] = {}
    metadata: dict[str, dict] = {}
    client: Any = None
    collection: str = "bindal_document_chunks"


state = EngineState()


def _load_engine() -> None:
    if not DATA_DIR.is_dir():
        raise RuntimeError(f"Data directory not found: {DATA_DIR}")
    file_data = load_files(str(DATA_DIR))
    state.metadata = load_crawler_documents(file_data)
    if not file_data:
        raise RuntimeError(f"No .txt documents found in {DATA_DIR}")
    state.file_data = file_data
    state.bm25_index = build_bm25_index(file_data)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _load_engine()
    state.client, state.collection = connect_qdrant()
    try:
        yield
    finally:
        state.client.close()
        state.client = None


app = FastAPI(
    title="Bindal Sach Engine",
    description="Hybrid document search with RRF and cross-encoder reranking",
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
        "pipeline": "hybrid_rrf_reranker",
    }


@app.get("/api/search", response_model=SearchResponse)
def search(
    q: str = Query(..., min_length=1, description="Search query"),
    top_k: int = Query(10, ge=1, le=50),
    candidate_k: int = Query(20, ge=1, le=100),
    semantic_k: int = Query(200, ge=1, le=1000),
) -> SearchResponse:
    query = q.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query must not be empty")

    if top_k > candidate_k:
        raise HTTPException(status_code=400, detail="top_k must not exceed candidate_k")
    if not state.bm25_index or state.client is None:
        raise HTTPException(status_code=503, detail="Search index is not ready")

    cleaned_query = remove_stopwords(query)
    try:
        raw_results = hybrid_search(query, client=state.client, collection=state.collection,
            bm25_index=state.bm25_index, documents=state.file_data, metadata=state.metadata,
            candidate_k=candidate_k, top_k=top_k, semantic_k=semantic_k)
    except Exception:
        logging.getLogger(__name__).exception("Hybrid search failed")
        raise HTTPException(status_code=503, detail="Hybrid search is temporarily unavailable. Please try again.") from None
    results = [
        SearchHit(
            file_name=item["document_name"], score=item["reranker_score"],
            snippet=[item["text"][:400]], text=item["text"],
            title=item.get("title"), url=item.get("url") or item.get("source_url"),
            source=item.get("source"), domain=item.get("domain"),
            chunk_id=item.get("chunk_id"), bm25_score=item.get("bm25_score"),
            semantic_score=item.get("semantic_score"), rrf_score=item["rrf_score"],
            reranker_score=item["reranker_score"],
        )
        for item in raw_results
    ]
    return SearchResponse(
        query=query,
        cleaned_query=cleaned_query,
        count=len(results),
        results=results,
    )


@app.get("/api/document")
def get_document(file_name: str = Query(..., min_length=1)) -> dict[str, str]:
    """Return only documents already loaded in the search corpus."""
    if file_name not in state.file_data:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"file_name": file_name, "text": state.file_data[file_name]}


class SummaryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    top_k: int = Field(default=3, ge=1, le=5)


@lru_cache(maxsize=1)
def get_summary_generator() -> RAGGenerator:
    return RAGGenerator()


@app.post("/api/summary", response_model=GenerationResponse)
def summarize(request: SummaryRequest) -> GenerationResponse:
    """Explicit opt-in generation from server-retrieved evidence only."""
    query = request.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query must not be empty")
    retrieved = search(q=query, top_k=10, candidate_k=20, semantic_k=200)
    context = build_context(query, [hit.model_dump() for hit in retrieved.results], top_k=request.top_k)
    try:
        return get_summary_generator().generate(query, context)
    except ConfigurationError:
        raise HTTPException(status_code=503, detail="AI summary is not configured. Set a Gemini API key on the server.") from None
    except GenerationError:
        raise HTTPException(status_code=502, detail="AI summary could not be generated. Please try again.") from None
    except ValueError:
        raise HTTPException(status_code=422, detail="The retrieved context is too large for a summary. Try a more specific query.") from None
    except Exception:
        raise HTTPException(status_code=503, detail="AI summary is temporarily unavailable. Please try again.") from None
