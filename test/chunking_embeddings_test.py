import pytest

from server.chunking import DocumentChunk, chunk_document, chunk_documents
from server.embeddings import EMBEDDING_DIMENSIONS, embed_chunks


def test_chunk_document_preserves_text_metadata_and_overlap():
    text = " ".join(f"word-{number}" for number in range(1, 501))

    chunks = chunk_document("guide.txt", text, chunk_words=250, overlap_words=40)

    assert len(chunks) == 3
    assert chunks[0].document_name == "guide.txt"
    assert chunks[0].chunk_id == "guide.txt::chunk-0"
    assert chunks[0].text == " ".join(f"word-{number}" for number in range(1, 251))
    assert chunks[1].text.startswith("word-211")
    assert chunks[1].text.endswith("word-460")


def test_chunk_documents_uses_file_loader_data_shape():
    chunks = chunk_documents({"one.txt": "alpha beta", "two.txt": "gamma"})

    assert [(chunk.document_name, chunk.text) for chunk in chunks] == [
        ("one.txt", "alpha beta"),
        ("two.txt", "gamma"),
    ]


class FakeEmbeddingModel:
    def encode(self, texts):
        return [[float(index)] * EMBEDDING_DIMENSIONS for index, _ in enumerate(texts)]


def test_embed_chunks_preserves_metadata_and_produces_384_dimensions():
    chunks = [DocumentChunk("guide.txt", "guide.txt::chunk-0", "Original text!")]

    embedded_chunks = embed_chunks(chunks, model=FakeEmbeddingModel())

    assert embedded_chunks[0].document_name == "guide.txt"
    assert embedded_chunks[0].chunk_id == "guide.txt::chunk-0"
    assert embedded_chunks[0].text == "Original text!"
    assert len(embedded_chunks[0].embedding) == 384


def test_embed_chunks_rejects_non_minilm_dimensions():
    class WrongSizeModel:
        def encode(self, texts):
            return [[0.0] * 10 for _ in texts]

    with pytest.raises(ValueError, match="384"):
        embed_chunks([DocumentChunk("guide.txt", "id", "text")], model=WrongSizeModel())
