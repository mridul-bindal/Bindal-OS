# Bindal-OS Search Engine Notes

## Project Purpose

Bindal-OS is a small document search engine built to demonstrate how search
engines tokenize documents, build indexes, rank results, and display snippets.
The current dataset contains ten MongoDB learning documents in `data/`.

## How To Run

Run the application from the project root:

```powershell
python main.py
```

Run the tests with:

```powershell
uv run python -m pytest
```

The project uses `pyproject.toml` for metadata, dependencies, and pytest
configuration. The development dependency is `pytest`.

## Folder Structure

```text
Bindal-OS/
├── main.py
├── client/
│   ├── __init__.py
│   └── app.py
├── server/
│   ├── __init__.py
│   ├── file_loader.py
│   └── search_engine/
│       ├── __init__.py
│       ├── benchmark.py
│       ├── indexing.py
│       ├── saveIndex.py
│       ├── search.py
│       ├── snippets.py
│       └── tokenizer.py
├── data/
├── test/
│   └── engine_test.py
├── pyproject.toml
├── uv.lock
└── .gitignore
```

`main.py` is only the application entry point. It imports `run` from the
client package.

`client/app.py` is the current console frontend. It loads the dataset, builds
the indexes, defines sample MongoDB queries, runs searches, and prints timing,
filenames, and snippets.

`server/file_loader.py` is responsible for reading only `.txt` documents from
the data directory. Generated JSON indexes are intentionally not treated as
search documents.

## Search Pipeline

The application follows this flow:

```text
TXT documents
    ↓
file loader
    ↓
tokenizer
    ↓
inverted indexes
    ↓
ranked search
    ↓
snippets and console output
```

### Tokenization

`tokenizer.py` converts text to lowercase and extracts letters and numbers
with a regular expression. For example, `"MongoDB, Version 7.0"` becomes:

```python
["mongodb", "version", "7", "0"]
```

Punctuation is removed and token matching is case-insensitive.

### Standard Inverted Index

`build_inverted_index()` maps each token to a set of filenames:

```python
{
    "mongodb": {"01_introduction.txt", "02_collections_documents.txt"},
    "sharding": {"08_sharding.txt"},
}
```

Sets prevent the same filename from being stored multiple times for one word.
`search_with_inverted_index()` uses this mapping instead of scanning every
document.

### Ranked Inverted Index

`build_ranked_inverted_index()` stores the frequency of each token per file:

```python
{
    "database": {
        "01_introduction.txt": 4,
        "04_indexing.txt": 2,
    }
}
```

`search_ranked_inverted_index()` adds the frequencies for matching query
tokens. Documents with larger scores appear first. The current implementation
matches documents containing *any* query token, rather than requiring every
query token.

### Snippets

`create_snippet()` finds query terms in the document and returns short text
windows around them. It removes newlines and returns at most three snippets by
default. The ranked snippet search returns the filename, score, and snippets.

### Timing

`benchmark.py` measures a search function with `time.perf_counter()` and
returns both the function result and elapsed time.

## Index Persistence

`saveIndex.py` stores these generated files:

```text
data/inverted_index.json
data/ranked_inverted_index.json
```

### Stopword Removal

Stopwords are common words that usually provide little meaning for search,
such as `the`, `is`, `in`, `and`, `to`, and `of`. Removing them reduces noise
and prevents frequent grammar words from affecting ranking.

For example:

```text
Original query:  the operating system and processes
Useful terms:    operating system processes
```


### TF-IDF 
Term frequency Inverse DOC FREQUENCY
LEST ASSUME a query system NLP 
AND 
two text files 
filwe1.txt -> {"system", "system" , ....} and 
file2.txt -> {"system", "nlp" , "modules"}

normal frequency would rank the first one above and keep the second one below which is a weaker retreival 

therefore we use tf-idf where idf is how rare this term is across all documents 
final score = term_frequency * inverse_document_frequency

in our code = result[tocken][file_name ] = term_frequency * udf

idf = math.log((total_docs+1)/(document_frequency+1))



Without stopword removal, a query such as `the database is corrupted` could
give too much weight to a document containing many repeated `the` and `is`
tokens. A document containing the meaningful terms `database corrupted`
should be more relevant.

The implementation is in `server/search_engine/stopwords.py`:

1. Split the query into whitespace-separated words.
2. Compare each word case-insensitively with the English stopword set.
3. Keep words that are not stopwords.
4. Join the remaining words into the cleaned query.

`client/app.py` calls `remove_stopwords()` before each search and prints the
cleaned query using `QUERY AFTER STOPWORD REMOVAL`. The search functions then
receive the cleaned query, so stopwords do not influence query matching or
ranking.

The project first tries to load English stopwords from the installed
`stopwords` package. A small built-in fallback set is used if that package is
not available, which allows `python main.py` to run without the optional
package installed in the active interpreter.

Stopwords are removed from both queries and document tokens before the
inverted, ranked, and TF-IDF indexes are built. The original document text is
kept unchanged so snippets still show natural sentences.

Current implementation detail: removal is whitespace-based, so punctuation can
prevent an exact match. For example, `the,` is not treated exactly like `the`.
The tokenizer already handles punctuation for search, so a future improvement
would be to tokenize the query first and remove stopwords from those tokens.

Python sets are converted to sorted lists before JSON serialization. The save
function does not overwrite an existing index file by default. The client
explicitly overwrites its generated index files when rebuilding them. The
generated JSON files are ignored by Git because they can be recreated from the
dataset.

Important: data-change detection and automatic index rebuilding are not yet
implemented. If a `.txt` dataset file changes, delete the generated JSON index
files manually before rebuilding them.

## Tests

`test/engine_test.py` tests the major behavior:

- Tokenization and punctuation handling
- File loading and directory ignoring
- Standard and ranked index construction
- Duplicate-word handling
- Basic and inverted-index searches
- Ranking behavior
- TF-IDF ranking, including a common term (`system`) and a rare term (`nlp`)
- Empty and unknown queries
- Snippet generation
- Index file creation and non-overwriting behavior
- Search timing

The pytest configuration points to `test/` and uses local ignored directories
for temporary files and cache data.

## Current Limitations

- The frontend is currently a console application; there is no web UI yet.
- Search history is not implemented yet, although it was part of the original
  project idea.
- Query matching uses simple token overlap and does not support phrases,
  stemming, fuzzy matching, or boolean operators. Stopword removal currently
  applies to queries only.
- TF-IDF uses exact token matches and summed term weights; it does not yet use
  document-length normalization or a more advanced relevance model.
- Index freshness checking is not implemented yet.
- The dataset is loaded into memory at startup.

## Git Notes

Commit source code, dataset text files, `pyproject.toml`, `uv.lock`, tests, and
documentation. Do not commit `.venv/`, Python caches, pytest caches, or
generated index JSON files. Never place passwords, API keys, or other secrets
in `pyproject.toml` or the repository.
