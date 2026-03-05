import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_lesson(client: AsyncClient):
    """Test creating a new lesson."""
    response = await client.post(
        "/api/v1/lessons",
        json={
            "agent_id": "test-agent",
            "task_context": "Handling customer refund request",
            "state_snapshot": {"order_status": "delivered"},
            "action_taken": "Processed full refund",
            "outcome": "success",
            "lesson_text": "Process refunds quickly for better satisfaction",
            "tags": ["refund", "customer-service"],
            "domain": "support",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["agent_id"] == "test-agent"
    assert data["outcome"] == "success"
    assert data["confidence"] == 1.0
    assert "id" in data


@pytest.mark.asyncio
async def test_list_lessons(client: AsyncClient):
    """Test listing lessons."""
    response = await client.get("/api/v1/lessons")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_list_lessons_with_filters(client: AsyncClient):
    """Test listing lessons with filters."""
    # Create a lesson first
    await client.post(
        "/api/v1/lessons",
        json={
            "agent_id": "filter-test-agent",
            "task_context": "Test context",
            "action_taken": "Test action",
            "outcome": "failure",
            "lesson_text": "Test lesson",
            "domain": "testing",
        },
    )

    response = await client.get(
        "/api/v1/lessons",
        params={"agent_id": "filter-test-agent", "domain": "testing"},
    )
    assert response.status_code == 200
    data = response.json()
    assert all(l["agent_id"] == "filter-test-agent" for l in data)
