from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class OutcomeRequest(BaseModel):
    """Request body for reporting a trace outcome."""

    trace_id: UUID = Field(..., description="ID of the trace whose outcome is being reported")
    outcome: str = Field(
        ...,
        pattern="^(success|failure|partial)$",
        description="Outcome of the trace: success, failure, or partial",
    )
    retrieved_lesson_ids: list[UUID] = Field(
        default_factory=list,
        description="Lesson IDs that were in context when the trace ran (for utility tracking)",
    )
    downstream_utility: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Estimated future utility (for Bellman discounting)",
    )
    context_similarity: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Similarity score used when retrieving these lessons",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "trace_id": "550e8400-e29b-41d4-a716-446655440000",
                "outcome": "success",
                "retrieved_lesson_ids": ["660e8400-e29b-41d4-a716-446655440001"],
                "downstream_utility": 0.0,
            }
        }
    )


class OutcomeResponse(BaseModel):
    """Response after recording a trace outcome."""

    trace_id: str
    outcome: str
    updated_lesson_ids: list[str]
    updated_count: int
