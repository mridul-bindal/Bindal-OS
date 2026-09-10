# Console benchmark entry point (compares search algorithms).
# For the web API, run: uv run uvicorn server.api:app --reload --host 127.0.0.1 --port 8000
from client import run


if __name__ == "__main__":
    run()
