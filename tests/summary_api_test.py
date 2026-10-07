from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from server import api
from server.ai.rag.generator import GenerationError, RAGGenerator
from server.ai.providers.gemini import ConfigurationError


@pytest.fixture
def setup(monkeypatch):
    search = Mock(return_value=api.SearchResponse(query="question", cleaned_query="question", count=1,
        results=[api.SearchHit(file_name="doc", text="Evidence", score=1, rrf_score=.03,
                              reranker_score=1, title="Title", url="https://example.com")]))
    generator = Mock()
    generator.generate.return_value = dict(answer="Answer [1]", sources=[dict(source_number=1,
        title="Title", url="https://example.com", domain="example.com", source=None)],
        insufficient_context=False, provider="fake", model="test")
    monkeypatch.setattr(api, "search", search)
    monkeypatch.setattr(api, "get_summary_generator", lambda: generator)
    return TestClient(api.app), search, generator


def test_summary_uses_server_retrieval_and_context(setup):
    client, search, generator = setup
    response = client.post('/api/summary', json={"query": " question "})
    assert response.status_code == 200
    assert response.json()['sources'][0]['url'] == 'https://example.com'
    search.assert_called_once_with(q="question", top_k=10, candidate_k=20, semantic_k=200)
    query, context = generator.generate.call_args.args
    assert query == context.query == "question"
    assert context.chunks[0].text == "Evidence"


@pytest.mark.parametrize('payload,status', [({"query":" "},400), ({"query":""},422),
    ({"query":"q","top_k":6},422), ({"query":"x"*4001},422)])
def test_bad_summary_requests(setup, payload, status):
    client, search, generator = setup
    assert client.post('/api/summary', json=payload).status_code == status
    search.assert_not_called()
    generator.generate.assert_not_called()


@pytest.mark.parametrize('error,status', [(ConfigurationError('secret'),503),
    (GenerationError('secret'),502), (ValueError('secret'),422), (RuntimeError('secret'),503)])
def test_generation_errors_are_safe(setup, error, status):
    client, _, generator = setup
    generator.generate.side_effect = error
    response = client.post('/api/summary', json={"query":"q"})
    assert response.status_code == status
    assert 'secret' not in response.text


def test_no_results_abstains_without_model_call(setup, monkeypatch):
    client, search, _ = setup
    search.return_value = api.SearchResponse(query="q",cleaned_query="q",count=0,results=[])
    model = Mock()
    monkeypatch.setattr(api, 'get_summary_generator', lambda: RAGGenerator(model=model))
    response = client.post('/api/summary',json={"query":"q"})
    assert response.status_code == 200 and response.json()['insufficient_context']
    model.invoke.assert_not_called()
