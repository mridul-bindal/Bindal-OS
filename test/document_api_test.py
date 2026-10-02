from fastapi.testclient import TestClient
from server.api import app, state


def test_document_returns_exact_indexed_text(monkeypatch):
    monkeypatch.setattr(state, "file_data", {"some file.txt": "Hello\n<script>plain text</script>"})
    response = TestClient(app).get("/api/document", params={"file_name": "some file.txt"})
    assert response.status_code == 200
    assert response.json() == {"file_name": "some file.txt", "text": "Hello\n<script>plain text</script>"}


def test_document_cannot_read_arbitrary_paths(monkeypatch):
    monkeypatch.setattr(state, "file_data", {"known.txt": "content"})
    client = TestClient(app)
    for name in ("missing.txt", "../semantic_search/.env", "D:/secret.txt"):
        assert client.get("/api/document", params={"file_name": name}).status_code == 404
    assert client.get("/api/document").status_code == 422
