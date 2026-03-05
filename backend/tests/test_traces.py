import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_trace(client: AsyncClient):
    """Test creating a new trace."""
    response = await client.post(
        "/api/v1/traces",
        params={"process_async": False},
        json={
            "agent_id": "test-agent",
            "trace_data": {
                "spans": [
                    {"name": "test_action", "status": "ok"}
                ]
            },
            "span_count": 1,
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["agent_id"] == "test-agent"
    assert data["status"] == "pending"
    assert "id" in data


@pytest.mark.asyncio
async def test_list_traces(client: AsyncClient):
    """Test listing traces."""
    # Create a trace first
    await client.post(
        "/api/v1/traces",
        params={"process_async": False},
        json={
            "agent_id": "list-test-agent",
            "trace_data": {"test": True},
            "span_count": 0,
        },
    )

    response = await client.get("/api/v1/traces")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
