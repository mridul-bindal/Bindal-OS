# AI preparation

`rag/` contains context preparation and optional LangChain generation.
`providers/` isolates Gemini configuration. Future AI summaries can live alongside
these modules. Context building itself remains offline; generation is opt-in.
No LangGraph or changes to retrieval are introduced.

```python
from server.ai.rag import build_context

# results = hybrid_search(...) using the existing retrieval pipeline
context = build_context(query, results, top_k=5)
payload = context.to_dict()          # query, chunk metadata/scores, formatted context
inputs = context.to_prompt_inputs()  # {"query": ..., "context": ...}
```

The builder accepts raw reranker dictionaries and serialized `/api/search`
results. It preserves their order, scores, original query and exact content.
`rank` is the original 1-based result position; `source_id` is the contiguous
1-based citation label after selection. Missing metadata stays `None` in the
structured output. Formatting uses the document name as a title fallback and
labels unavailable fields. A domain can be inferred from an available URL.

Selection skips empty text and keeps the first occurrence of a document name
or exact URL, repeated document/chunk IDs, and identical text. `top_k` applies
after deduplication. Set `deduplicate_documents=False` to allow different chunks
from the same document; repeated chunks and exact text still collapse. This is
exact matching, not semantic or near-duplicate detection.

BM25-only results can contain full-document text with no chunk ID. These remain
explicitly document-level evidence; no new chunks or invented IDs are created.
The layer does not truncate text or enforce a token budget. A future model
adapter should budget context for its model and treat all source text as
untrusted evidence, not instructions. Source labels alone do not prevent prompt
injection. No answers or relevance judgments are generated here.

## Real retrieval example

With the existing API running on localhost:8000:

```powershell
uv run python -m evaluation.rag_context_demo --query "What is SQL injection?" --top-k 2
```

The demo performs a read-only search through the existing API and saves the
resulting context in `evaluation/results/rag_context_example.json` and `.txt`.
If the API server is stopped, add `--in-process` to use its unchanged application
lifecycle locally. This still uses real Qdrant and retrieval models.


## Gemini generation

Install locked dependencies with `uv sync`. Copy the root `.env.example` to
`.env` and set `GOOGLE_API_KEY` (or `GEMINI_API_KEY`). Set `GEMINI_MODEL` to a model
available to your account; the default is `gemini-2.5-flash`. Environment variables
win over `.env`. The existing `server/semantic_search/.env` is also loaded as a fallback,
without overriding the environment or root `.env`. Never commit keys.

```python
from server.ai.rag.generator import RAGGenerator

generator = RAGGenerator(max_chunks=5, max_context_chars=24000, timeout=60)
response = generator.generate(query, context)
payload = response.model_dump()
```

Reuse the generator to reuse its chat client. A caller can inject a different
LangChain chat model via `model=`, with `provider=` and `model_name=` metadata.
Injected models must configure their own transport timeouts/retries; the timeout
argument controls the default Gemini adapter. No tools, browsing or search are
bound to the model. LangChain is used for the chat abstraction, prompt template,
invocation and Pydantic output parsing, not retrieval.

Limits are validated before any request: at most 5 chunks, 24,000 formatted
context characters, 4,000 query characters and 2,048 output tokens by default.
All are constructor options. Character limits are not exact token counts.
Oversized contexts raise ValueError; select fewer chunks through the unchanged
context builder. Query and context.query must match exactly.

Sources in the response come exclusively from context metadata. Model output
contains answer, cited source numbers and an insufficient-context flag; URLs and
source metadata are never accepted from model output. Numeric inline citations
must match the cited list and known source IDs. Invalid responses fail closed.
Valid citation numbers alone do not prove that a claim is supported; semantic
faithfulness still needs evaluation. Empty context makes no model call. Declared
insufficient context returns a fixed explicit abstention. API/timeout errors raise
GenerationError; malformed output raises MalformedResponseError. These are not
converted into successful answers. Gemini requests use a 60-second transport
timeout and zero automatic retries by default.

Run the full read-only retrieval and generation demo (one real Gemini call):

```powershell
uv run python -m evaluation.rag_generation_demo --query "What is SQL injection?" --top-k 3
```

It prints the query, retrieved sources, answer, verified references, generation
time and total pipeline time. Successful runs save
`evaluation/results/rag_generation_example.json`. A missing key fails before
loading retrieval models. Tests use mocked models and no live generation calls.

Provider implementation reference:
[LangChain Gemini integration](https://docs.langchain.com/oss/python/integrations/chat/google_generative_ai).


## Frontend AI summary

Search normally, then click **Generate summary** above the results. Generation
is optional and never runs as part of an ordinary search request. The existing
layout and search results remain visible. Source references open their original
pages. A new search clears the summary and cancels the browser's pending request
(the server may still finish a provider call already in progress).

`POST /api/summary` accepts `{ "query": "...", "top_k": 3 }` (top_k 1?5).
It calls the unchanged search pipeline, builds context and invokes the generator.
It never trusts browser-supplied evidence. The cached generator reuses its model;
restart the backend after changing credentials. Missing configuration, provider
failure and context limits produce explicit errors with a retry option in the UI.
