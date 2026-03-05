import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_retrieve_lessons(client: AsyncClient):
    """Test retrieving lessons by similarity."""
    response = await client.post(
        "/api/v1/retrieve",
        json={
            "query": "How should I handle a customer refund?",
            "top_k": 5,
            "min_confidence": 0.0,
            "include_context": True,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert "lessons" in data
    assert "total" in data
    assert isinstance(data["lessons"], list)


@pytest.mark.asyncio
async def test_retrieve_with_filters(client: AsyncClient):
    """Test retrieving lessons with agent and domain filters."""
    response = await client.post(
        "/api/v1/retrieve",
        json={
            "query": "error handling best practices",
            "agent_id": "test-agent",
            "domain": "support",
            "top_k": 3,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert "lessons" in data
