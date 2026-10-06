"""Manual live verification for the user-supplied page; uses existing functions."""
import json
from pathlib import Path
from qdrant_client import models
from server.crawler import crawl_url
from server.crawler.chunking import chunk_crawled_document
from server.crawler.indexing import index_crawled_chunks
from server.semantic_search.vector_store import connect_qdrant
from server.semantic_search.search import semantic_search
from server.search_engine.BM25 import search_bm25_index
from server.hybrid_search import reciprocal_rank_fusion
from server.reranking import rerank

url = 'https://www.geeksforgeeks.org/mongodb/mongodb-replication-and-sharding/'
document = json.loads(Path('data/crawler/documents/108762a771e14cae709c8bdd4c5b5383dfa96f90d8a7dc1174f71861e957be97.json').read_text(encoding='utf-8'))
chunks = chunk_crawled_document(document)
duplicate = crawl_url(url)
assert duplicate['is_duplicate'] is True
assert chunk_crawled_document(duplicate) == []
print(f'Chunks: {len(chunks)}; duplicate crawl skipped: True', flush=True)
client, collection = connect_qdrant()
try:
    before = client.count(collection, exact=True).count
    indexed = index_crawled_chunks(chunks, client=client, collection=collection)
    after = client.count(collection, exact=True).count
    indexed = index_crawled_chunks(chunks, client=client, collection=collection)
    repeat = client.count(collection, exact=True).count
    assert repeat == after
    points, _ = client.scroll(collection, scroll_filter=models.Filter(must=[models.FieldCondition(
        key='source', match=models.MatchValue(value=f'crawler:{url}'))]), limit=len(chunks)+1, with_payload=True)
    assert len(points) == len(chunks)
    for point in points:
        original = next(c for c in chunks if c.chunk_id == point.payload['chunk_id'])
        for key in ('source_url', 'title', 'content_hash', 'crawled_at', 'document_name', 'chunk_id', 'text'):
            assert point.payload[key] == getattr(original, key)
    query = 'What is the difference between replication and sharding in MongoDB?'
    bm25 = search_bm25_index(query, indexed['bm25_index'])
    semantic = semantic_search(query, client=client, collection=collection, top_k=after)
    fused = reciprocal_rank_fusion(bm25, semantic)
    final = rerank(query, fused, candidate_k=20, top_k=5,
                   document_metadata={chunks[0].document_name: {'source_url': url, 'title': document['title']}})
    target = chunks[0].document_name
    def rank(names):
        return names.index(target)+1 if target in names else None
    summary = {'url': url, 'title': document['title'], 'characters': len(document['text']),
        'chunks': len(chunks), 'duplicate_skipped': True, 'metadata_verified': True,
        'collection': collection, 'points_before': before, 'points_after': after,
        'points_after_reindex': repeat, 'query': query,
        'bm25_rank': rank([r['file_name'] for r in bm25]),
        'semantic_first_chunk_rank': rank([r.document_name for r in semantic]),
        'rrf_rank': rank([r.document_name for r in fused]),
        'reranked_top5_rank': rank([r['document_name'] for r in final]),
        'note': 'BM25 uses the crawler-only manifest; semantic search covers the entire collection.'}
    Path('data/crawler/index/workflow_check.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary, indent=2), flush=True)
finally:
    client.close()
