# Repository layout migration

| Previous location | Current location |
| --- | --- |
| `client/my-react-app/` | `frontend/` |
| `client/app.py`, `client/__init__.py` | `scripts/` |
| `test/` | `tests/` |
| `notes.md` | `docs/notes.md` |
| `inverted_index.png` | `docs/assets/inverted_index.png` |
| `crawler_output/` | `data/crawler/documents/` |
| `crawler_index/` | `data/crawler/index/` |
| `crawler_runs/` | `data/crawler/runs/` |
| `crawler_index/check_workflow.py` | `evaluation/check_workflow.py` |
| Generated `data/*.json` indexes | `data/indexes/` |
| Historical `data/embedded_chunks.json` | `data/legacy/embedded_chunks.json` |

Existing crawler files were moved, not regenerated. SQLite `document_path`
references were updated to the relocated documents. Each frontier has a
`frontier.before-layout.sqlite3` backup of its pre-migration state. Those backups
contain old paths and should not replace the migrated frontier during normal use.
Saved historical report JSON remains unchanged as a record of its original run.
Use the new paths for future commands and external scripts.

The backend's `server.*` imports, Qdrant collection, vector IDs, credentials,
retrieval algorithms and corpus content are unchanged. The `main.py` console
entry point is retained. The frontend now starts from `frontend/`.
