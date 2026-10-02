"""Structure-aware chunks bounded by the actual MiniLM tokenizer/input budget."""
from dataclasses import dataclass
from functools import lru_cache
import re
from .chunking import DocumentChunk

TOKENIZER_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


@lru_cache(maxsize=1)
def get_token_counter():
    from .embeddings import get_embedding_model
    model = get_embedding_model()
    return TokenCounter(model.tokenizer, model.max_seq_length)


class TokenCounter:
    def __init__(self, tokenizer, model_limit):
        self.tokenizer, self.model_limit = tokenizer, model_limit

    def count(self, text):
        return len(self.tokenizer.encode(text, add_special_tokens=True, truncation=False, verbose=False))

    def offsets(self, text):
        return self.tokenizer(text, add_special_tokens=False, truncation=False,
                              return_offsets_mapping=True, verbose=False)["offset_mapping"]


@dataclass(frozen=True)
class StructuredDocumentChunk(DocumentChunk):
    heading_path: tuple[str, ...]
    chunk_index: int
    token_count: int
    chunking_config: dict


def chunk_structured_document(document_name, text, *, blocks=None,
                              target_chunk_tokens=200, max_chunk_tokens=300,
                              overlap_tokens=40, token_counter=None):
    for name, value in (("target_chunk_tokens", target_chunk_tokens), ("max_chunk_tokens", max_chunk_tokens),
                        ("overlap_tokens", overlap_tokens)):
        if isinstance(value, bool) or not isinstance(value, int) or value < (0 if name == "overlap_tokens" else 1):
            raise ValueError(f"Invalid {name}")
    if target_chunk_tokens > max_chunk_tokens or overlap_tokens >= target_chunk_tokens:
        raise ValueError("Require overlap_tokens < target_chunk_tokens <= max_chunk_tokens")
    if not text.strip():
        return []
    counter = token_counter or get_token_counter()
    limit = min(max_chunk_tokens, counter.model_limit)
    target = min(target_chunk_tokens, limit)
    if overlap_tokens >= target or limit <= counter.count(""):
        raise ValueError("Token settings leave no embedding input budget")
    if blocks is None:
        blocks = [{"kind": "paragraph", "text": p} for p in re.split(r"\n\s*\n", text) if p.strip()]
    sections, path, body = [], [], []
    for block in blocks:
        if not isinstance(block.get("text"), str):
            raise ValueError("Block text must be a string")
        if block["kind"] == "heading":
            if body or (path and block["level"] <= path[-1][0]):
                sections.append((tuple(value for _, value in path), body))
                body = []
            level = block["level"]
            path = [(n, value) for n, value in path if n < level]
            path.append((level, block["text"]))
        elif block["text"].strip():
            body.append(block)
    if body or path:
        sections.append((tuple(value for _, value in path), body))
    results = []
    config = {"strategy": "structure_tokens_v1", "target_chunk_tokens": target_chunk_tokens,
              "max_chunk_tokens": max_chunk_tokens, "overlap_tokens": overlap_tokens,
              "effective_max_tokens": limit, "tokenizer_model": TOKENIZER_MODEL}

    def prefix_slice(value, budget):
        end = 0
        for _, stop in counter.offsets(value):
            if counter.count(value[:stop]) > budget:
                break
            end = stop
        return value[:end]

    for headings, section_blocks in sections:
        prefix = "\n".join(headings)
        if counter.count(prefix) > max(counter.count(""), limit // 3):
            prefix = prefix_slice(prefix, max(counter.count("") + 1, limit // 3))
        def compose(value):
            return (prefix + "\n\n" + value).strip("\r\n") if prefix else value.strip("\r\n")
        def emit(value):
            rendered = compose(value)
            if not rendered:
                return
            if counter.count(rendered) > limit:
                raise ValueError("Chunk exceeds embedding token budget")
            i = len(results)
            results.append(StructuredDocumentChunk(document_name, f"{document_name}::chunk-{i}",
                           rendered, headings, i, counter.count(rendered), dict(config)))

        whole = "\n\n".join(b["text"] for b in section_blocks)
        if counter.count(compose(whole)) <= limit:
            emit(whole)
            continue
        pending, previous = "", ""
        def with_overlap(value):
            if not previous or not overlap_tokens:
                return value
            offsets = counter.offsets(previous)
            tail = previous[offsets[max(0, len(offsets) - overlap_tokens)][0]:] if offsets else ""
            while tail and counter.count(tail) - counter.count("") > overlap_tokens:
                positions = counter.offsets(tail)
                tail = tail[positions[1][0]:] if len(positions) > 1 else ""
            return tail + "\n\n" + value if counter.count(compose(tail + "\n\n" + value)) <= limit else value
        for block in section_blocks:
            value = block["text"]
            if counter.count(compose(value)) <= limit:
                merged = pending + "\n\n" + value if pending else with_overlap(value)
                if pending and (counter.count(compose(merged)) > limit or counter.count(compose(pending)) >= target):
                    emit(pending)
                    previous, pending = pending, ""
                    merged = with_overlap(value)
                pending = merged
                continue
            if pending:
                emit(pending)
                previous, pending = pending, ""
            remaining = value
            while remaining.strip():
                if counter.count(compose(remaining)) <= limit:
                    pending = with_overlap(remaining)
                    break
                stop = 0
                for _, end in counter.offsets(remaining):
                    if counter.count(compose(remaining[:end])) > target:
                        break
                    stop = end
                if stop == 0:
                    raise ValueError("No content token fits beside heading context")
                if block["kind"] == "code" and "\n" in remaining[:stop]:
                    stop = remaining.rfind("\n", 0, stop) + 1
                piece = remaining[:stop]
                emit(with_overlap(piece))
                previous = piece
                remaining = remaining[stop:]
        if pending:
            emit(pending)
    return results
