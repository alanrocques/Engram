import pytest


def test_generate_embedding():
    """Test embedding generation with sentence-transformers."""
    from app.services.embedding import generate_embedding

    text = "How should I handle a customer refund request?"
    embedding = generate_embedding(text)

    assert isinstance(embedding, list)
    assert len(embedding) == 384  # BAAI/bge-small-en-v1.5 produces 384-dim vectors
    assert all(isinstance(x, float) for x in embedding)


def test_generate_embeddings_batch():
    """Test batch embedding generation."""
    from app.services.embedding import generate_embeddings_batch

    texts = [
        "Handle refund requests promptly",
        "Always verify customer identity",
        "Log all support interactions",
    ]
    embeddings = generate_embeddings_batch(texts)

    assert len(embeddings) == 3
    assert all(len(emb) == 384 for emb in embeddings)
