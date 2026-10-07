import json
from unittest.mock import Mock

import pytest
from langchain_core.messages import AIMessage

from server.ai.rag import build_context
from server.ai.rag.generator import RAGGenerator, GenerationError, MalformedResponseError
from server.ai.rag.prompts import INSUFFICIENT_CONTEXT
from server.ai.providers import gemini


def context():
    return build_context("What is SQL injection?", [{"document_name": "a", "text": "SQLi manipulates SQL.",
        "title": "SQL injection", "url": "https://example.com/sql", "source": "gfg", "chunk_id": "a-0"}])


def model(answer="SQLi manipulates SQL. [1]", ids=None, insufficient=False):
    return Mock(invoke=Mock(return_value=AIMessage(content=json.dumps({"answer": answer,
        "source_numbers": [1] if ids is None else ids, "insufficient_context": insufficient}))))


def test_prompt_and_source_preservation():
    c = context(); llm = model()
    response = RAGGenerator(model=llm, provider="fake", model_name="test").generate(c.query, c)
    messages = llm.invoke.call_args.args[0].to_messages()
    assert messages[0].type == "system"
    assert "USER QUERY\nWhat is SQL injection?\n\nRETRIEVED CONTEXT\n[Source 1]" in messages[1].content
    assert "not as instructions" in messages[0].content
    assert response.sources[0].model_dump() == {"source_number": 1, "title": "SQL injection",
        "url": "https://example.com/sql", "domain": "example.com", "source": "gfg"}
    assert response.provider == "fake" and response.model == "test"


def test_empty_context_never_invokes_provider():
    llm = model(); c = build_context("query", [])
    result = RAGGenerator(model=llm).generate(c.query, c)
    assert result.insufficient_context and result.answer == INSUFFICIENT_CONTEXT
    assert result.sources == [] and result.provider is None
    llm.invoke.assert_not_called()


def test_insufficient_context_is_explicit():
    c = context()
    result = RAGGenerator(model=model("Not enough evidence", [], True)).generate(c.query, c)
    assert result.answer == INSUFFICIENT_CONTEXT and result.sources == []


@pytest.mark.parametrize("answer,ids", [("Unknown [2]", [2]), ("No citation", [1]),
    ("Unknown [1] [9]", [1]), ("See https://fake.com [1]", [1]), ("   ", []), ("Uncited", [])])
def test_invalid_citations(answer, ids):
    c = context()
    with pytest.raises(MalformedResponseError):
        RAGGenerator(model=model(answer, ids)).generate(c.query, c)


@pytest.mark.parametrize("content", ["not json", "{}", '{"answer": 123}', ""])
def test_malformed_response(content):
    c = context(); llm = Mock(invoke=Mock(return_value=AIMessage(content=content)))
    with pytest.raises(MalformedResponseError): RAGGenerator(model=llm).generate(c.query, c)


@pytest.mark.parametrize("error", [TimeoutError("secret"), RuntimeError("secret")])
def test_provider_failure_is_not_fabricated(error):
    c = context(); llm = Mock(invoke=Mock(side_effect=error))
    with pytest.raises(GenerationError) as exc: RAGGenerator(model=llm).generate(c.query, c)
    assert "secret" not in str(exc.value)


@pytest.mark.parametrize("kwargs", [{"max_context_chars": 1}, {"max_query_chars": 1}])
def test_limits_before_invocation(kwargs):
    c = context(); llm = model()
    with pytest.raises(ValueError): RAGGenerator(model=llm, **kwargs).generate(c.query, c)
    llm.invoke.assert_not_called()


def test_chunk_limit_and_query_validation():
    c = build_context("query", [{"document_name": str(i), "text": str(i)} for i in range(2)])
    llm = model(); generator = RAGGenerator(model=llm, max_chunks=1)
    for query in ("query", "", "different"):
        with pytest.raises(ValueError): generator.generate(query, c)
    llm.invoke.assert_not_called()


def test_missing_key(monkeypatch):
    monkeypatch.setattr(gemini, "load_dotenv", Mock())
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(gemini.ConfigurationError, match="GOOGLE_API_KEY"): gemini.create_model()


def test_provider_config_no_network(monkeypatch):
    import langchain_google_genai
    monkeypatch.setattr(gemini, "load_dotenv", Mock())
    monkeypatch.setenv("GOOGLE_API_KEY", "test-only")
    monkeypatch.setenv("GEMINI_MODEL", "test-model")
    factory = Mock(); monkeypatch.setattr(langchain_google_genai, "ChatGoogleGenerativeAI", factory)
    gemini.create_model(timeout=12, max_output_tokens=512)
    assert factory.call_args.kwargs == dict(model="test-model", api_key="test-only", vertexai=False,
        timeout=12, max_retries=0, max_tokens=512, response_mime_type="application/json")


def test_noncontiguous_source_numbers_not_renumbered():
    from dataclasses import replace
    c = context(); c = replace(c, chunks=(replace(c.chunks[0], source_id=7),))
    result = RAGGenerator(model=model("Supported [7]", [7])).generate(c.query, c)
    assert result.sources[0].source_number == 7


def test_grouped_citations_validate_every_source_number():
    from dataclasses import replace
    c = context()
    c = replace(c, chunks=(c.chunks[0], replace(c.chunks[0], source_id=2)))
    result = RAGGenerator(model=model("Supported [1, 2]", [1, 2])).generate(c.query, c)
    assert [s.source_number for s in result.sources] == [1, 2]
    with pytest.raises(MalformedResponseError):
        RAGGenerator(model=model("Unsupported [1, 9]", [1, 9])).generate(c.query, c)
