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
    outcome: str = Field(
        default="unknown",
        pattern="^(success|failure|partial|unknown)$",
        description="Outcome of the trace for extraction routing",
    )

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
                "outcome": "success",
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
    content_hash: str | None = None
    outcome: str | None = None
    extraction_mode: str | None = None
    is_influenced: bool = False
    retrieved_lesson_ids: list[UUID] = []

    model_config = ConfigDict(from_attributes=True)


class TraceBatchCreate(BaseModel):
    """Schema for batch trace ingestion."""

    agent_id: str = Field(..., min_length=1, max_length=255)
    traces: list[dict[str, Any]] = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Array of trace data objects (max 50)",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "agent_id": "support-bot-v2",
                "traces": [
                    {"action": "handle_refund", "result": "success"},
                    {"action": "send_email", "result": "success"},
                ],
            }
        }
    )


class TraceBatchResponse(BaseModel):
    """Response schema for batch trace ingestion."""

    created: int = Field(..., description="Number of traces created")
    skipped: int = Field(..., description="Number of traces skipped (duplicates)")
    trace_ids: list[str] = Field(..., description="IDs of created traces")


class TraceDeleteBulk(BaseModel):
    """Schema for bulk trace deletion."""

    ids: list[UUID] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Trace IDs to delete (max 100)",
    )
