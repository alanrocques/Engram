from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TraceStatus(str, Enum):
    """Status of trace processing."""

    PENDING = "pending"
    PROCESSED = "processed"
    FAILED = "failed"


class TraceCreate(BaseModel):
    """Schema for creating a new trace."""

    agent_id: str = Field(..., min_length=1, max_length=255)
    trace_data: dict[str, Any] = Field(..., description="Raw trace data from agent")
    span_count: int = Field(default=0, ge=0)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "agent_id": "support-bot-v2",
                "trace_data": {
                    "spans": [
                        {
                            "name": "handle_refund_request",
                            "status": "ok",
                            "attributes": {"user_id": "123"},
                        }
                    ]
                },
                "span_count": 1,
            }
        }
    )


class TraceResponse(BaseModel):
    """Schema for trace response."""

    id: UUID
    agent_id: str
    trace_data: dict[str, Any]
    span_count: int
    status: TraceStatus
    created_at: datetime
    processed_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
