# Shared technical lexical normalization

`tokenizer.tokenize` is used consistently by document indexing and query processing.
BM25 scoring is unchanged. The representation version is `technical-v2`.
The API passes the original query into this shared representation; its cleaned
query is display metadata only, so stopword removal cannot accidentally create
new adjacent compounds that document indexing would not produce.

- Unicode NFC and case folding normalize case without a technology dictionary.
- Preserve complete technical tokens: `$lookup`, `$group`, `C++`, `C#`, `.NET`,
  `Node.js`, `React.js`, `shard-key`, and underscore identifiers.
- Internal dot/hyphen/underscore compounds also emit component and compact aliases:
  `Node.js` produces `node.js`, `node`, `js`, `nodejs`.
- Adjacent alphanumeric pairs emit a compact alias, so `node js` and `redis cache`
  can match `Node.js` and `RedisCache`. Case-insensitive processing is identical
  for documents and queries. It does not guess boundaries inside lowercase words.
- Pair aliases are bounded to two terms and 48 characters, exclude stopwords,
  repeated terms and one-character components, and never cross punctuation or
  line endings. Pure numeric versions keep their punctuation: `1.2` is not `12`.
- Symbol-bearing terms are not aliased to stripped forms: C, C++, and C# stay
  distinct, as do `$lookup`/`lookup` and `.NET`/`net`.

This is a recall-oriented representation, not proof that two phrases mean the
same thing. Some compact-word/phrase ambiguity remains (for example `black bird`
versus `blackbird`), and adding aliases changes term frequencies/document lengths.
Compound boundaries beyond two words are intentionally not guessed. No synonyms,
stemming, technology-specific replacements, or BM25 formula changes are added.

All persisted lexical indexes must be rebuilt. Restart the API to rebuild its
in-memory BM25 index. For the full requested local/crawler migration and live checks:

```powershell
uv run python -m evaluation.validate_structure "https://www.geeksforgeeks.org/mongodb/mongodb-replication-and-sharding/"
```

This explicitly rewrites local lexical indexes, rebuilds local Qdrant chunks,
recrawls/reindexes the supplied URL, verifies model token limits and idempotence,
and saves `evaluation/structure_validation.json`. Earlier evaluation reports are
historical snapshots and do not describe the migrated representation.
