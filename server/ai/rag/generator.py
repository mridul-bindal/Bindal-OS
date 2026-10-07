"""Bounded grounded generation, independent of retrieval implementations."""
import math
import re
from typing import Any

from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt

from .context import RAGContext
from .prompts import INSUFFICIENT_CONTEXT, generation_prompt


class GenerationError(RuntimeError):
    """Provider failure; no fabricated fallback answer."""


class MalformedResponseError(GenerationError):
    pass


class ModelAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answer: str = Field(min_length=1)
    source_numbers: list[StrictInt]
    insufficient_context: StrictBool


class SourceReference(BaseModel):
    source_number: int
    title: str
    url: str | None
    domain: str | None
    source: str | None


class GenerationResponse(BaseModel):
    answer: str
    sources: list[SourceReference]
    insufficient_context: bool
    provider: str | None = None
    model: str | None = None


class RAGGenerator:
    """Reuse an instance across queries. Inject another LangChain chat model to switch providers.

    Limits reject oversized input, never reselect or truncate the builder's chunks.
    max_context_chars measures the complete formatted context, not model tokens.
    """
    def __init__(self, *, model: Any = None, provider: str | None = None,
                 model_name: str | None = None, max_chunks: int = 5,
                 max_context_chars: int = 24000, max_query_chars: int = 4000,
                 timeout: float = 60, max_output_tokens: int = 2048):
        for name, value in (("max_chunks", max_chunks), ("max_context_chars", max_context_chars),
                            ("max_query_chars", max_query_chars), ("max_output_tokens", max_output_tokens)):
            if type(value) is not int or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if isinstance(timeout, bool) or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be positive and finite")
        self.model = model
        self.provider = provider if model is not None else "gemini"
        self.model_name = model_name
        self.max_chunks, self.max_context_chars = max_chunks, max_context_chars
        self.max_query_chars = max_query_chars
        self.timeout, self.max_output_tokens = timeout, max_output_tokens

    def generate(self, query: str, context: RAGContext) -> GenerationResponse:
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must be non-empty")
        if not isinstance(context, RAGContext) or query != context.query:
            raise ValueError("query must match the RAGContext query")
        if len(query) > self.max_query_chars or len(context.chunks) > self.max_chunks:
            raise ValueError("Query or chunk count exceeds configured limits")
        formatted = context.format_context()
        if len(formatted) > self.max_context_chars:
            raise ValueError("Context exceeds max_context_chars; select fewer chunks with the context builder")
        if not context.chunks:
            return GenerationResponse(answer=INSUFFICIENT_CONTEXT, sources=[], insufficient_context=True)
        sources = {c.source_id: c for c in context.chunks}
        if (len(sources) != len(context.chunks) or
            any(type(c.source_id) is not int or c.source_id <= 0 or not c.text.strip() for c in context.chunks)):
            raise ValueError("Context must contain unique positive source IDs and non-empty text")
        if self.model is None:
            from server.ai.providers.gemini import create_model
            self.model, self.model_name = create_model(timeout=self.timeout, max_output_tokens=self.max_output_tokens)
        parser = PydanticOutputParser(pydantic_object=ModelAnswer)
        prompt = generation_prompt().invoke({"query": query, "context": formatted,
                                             "format_instructions": parser.get_format_instructions()})
        try:
            message = self.model.invoke(prompt)
        except Exception:
            # Provider errors may contain request bodies or credentials; do not propagate them.
            raise GenerationError("LLM request failed or timed out; no answer was generated") from None
        try:
            result = parser.invoke(message)
        except Exception:
            raise MalformedResponseError("LLM returned an invalid structured response") from None
        numbers = set(result.source_numbers)
        inline = {int(n.strip())
                  for group in re.findall(r"\[(\d+(?:\s*,\s*\d+)*)\]", result.answer)
                  for n in group.split(",")}
        if (not result.answer.strip() or not numbers.issubset(sources) or
            not inline.issubset(sources) or numbers != inline or
            re.search(r"https?://|www\.", result.answer, re.I)):
            raise MalformedResponseError("LLM response contains invalid citations or unsupported URL formatting")
        if result.insufficient_context:
            return GenerationResponse(answer=INSUFFICIENT_CONTEXT, sources=[], insufficient_context=True,
                                      provider=self.provider, model=self.model_name)
        if not numbers:
            raise MalformedResponseError("A grounded answer must cite at least one supplied source")
        references = [SourceReference(source_number=c.source_id, title=c.title or c.document_name,
                       url=c.url, domain=c.domain, source=c.source)
                      for c in context.chunks if c.source_id in numbers]
        return GenerationResponse(answer=result.answer, sources=references, insufficient_context=False,
                                  provider=self.provider, model=self.model_name)
