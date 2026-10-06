"""Project-local storage paths, independent of the working directory."""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
LOCAL_INDEX_DIR = DATA_DIR / "indexes"
CRAWLER_DIR = DATA_DIR / "crawler"
CRAWLER_DOCUMENTS_DIR = CRAWLER_DIR / "documents"
CRAWLER_INDEX_FILE = CRAWLER_DIR / "index" / "index.json"
CRAWLER_RUNS_DIR = CRAWLER_DIR / "runs"
