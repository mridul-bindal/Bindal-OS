"""Application orchestration using the existing retrieval stages."""
import json
from server.crawler.indexing import DEFAULT_INDEX_FILE
from server.search_engine.BM25 import search_bm25_index
from server.semantic_search.search import semantic_search
from server.hybrid_search import reciprocal_rank_fusion
from server.reranking import rerank


def load_crawler_documents(file_data):
    metadata = {name: {"text": text} for name, text in file_data.items()}
    if DEFAULT_INDEX_FILE.exists():
        manifest = json.loads(DEFAULT_INDEX_FILE.read_text(encoding="utf-8"))
        for url, document in manifest["documents"].items():
            name = document["document_name"]
            file_data[name] = document["text"]
            chunk = document["chunks"][0] if document.get("chunks") else {}
            metadata[name] = {"text": document["text"], "url": url, "title": chunk.get("title"),
                              "source": chunk.get("source"), "domain": chunk.get("domain")}
    return metadata


def hybrid_search(query, *, client, collection, bm25_index, documents, metadata,
                  candidate_k=20, top_k=10, semantic_k=200):
    lexical = search_bm25_index(query, bm25_index)
    semantic = semantic_search(query, client=client, collection=collection, top_k=semantic_k)
    semantic = [hit for hit in semantic if hit.document_name in documents]
    candidates = reciprocal_rank_fusion(lexical, semantic)
    enriched = {name: {"text": text, **metadata.get(name, {})} for name, text in documents.items()}
    return rerank(query, candidates, candidate_k=candidate_k, top_k=top_k, document_metadata=enriched)
