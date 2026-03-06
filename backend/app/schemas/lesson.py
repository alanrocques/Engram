from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class OutcomeType(str, Enum):
    """Outcome of an agent action."""

    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"


class LessonCreate(BaseModel):
    """Schema for creating a new lesson."""

    agent_id: str = Field(..., min_length=1, max_length=255)
    task_context: str = Field(..., min_length=1, description="What the agent was trying to do")
    state_snapshot: dict[str, Any] = Field(
        default_factory=dict, description="Environment state when lesson was learned"
    )
    action_taken: str = Field(..., min_length=1, description="What the agent did")
    outcome: OutcomeType = Field(..., description="Result of the action")
    lesson_text: str = Field(..., min_length=1, description="Distilled takeaway")
    tags: list[str] = Field(default_factory=list)
    source_trace_id: UUID | None = Field(default=None)
    domain: str = Field(default="general", max_length=100)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "agent_id": "support-bot-v2",
                "task_context": "Handle customer refund request for order #456",
                "state_snapshot": {"order_status": "delivered", "days_since_delivery": 3},
                "action_taken": "Processed full refund without requiring return",
                "outcome": "success",
                "lesson_text": "For orders delivered within 7 days, process refund immediately without return requirement to improve customer satisfaction.",
                "tags": ["refund", "customer-service"],
                "domain": "support",
            }
        }
    )


class LessonUpdate(BaseModel):
    """Schema for updating a lesson."""

    task_context: str | None = Field(default=None, min_length=1)
    action_taken: str | None = Field(default=None, min_length=1)
    outcome: OutcomeType | None = None
    lesson_text: str | None = Field(default=None, min_length=1)
    tags: list[str] | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    domain: str | None = Field(default=None, max_length=100)
    is_archived: bool | None = Field(default=None, description="Archive/unarchive the lesson")


class LessonResponse(BaseModel):
    """Schema for lesson response."""

    id: UUID
    agent_id: str
    task_context: str
    state_snapshot: dict[str, Any]
    action_taken: str
    outcome: OutcomeType
    lesson_text: str
    confidence: float
    created_at: datetime
    last_validated: datetime | None = None
    tags: list[str]
    source_trace_id: UUID | None = None
    version: int
    domain: str
    is_archived: bool = False
    has_conflict: bool = False
    conflict_ids: list[UUID] = Field(default_factory=list)
    utility: float = 0.5
    retrieval_count: int = 0
    success_count: int = 0
    last_retrieved_at: datetime | None = None
    lesson_type: str = "general"
    extraction_mode: str | None = None
    parent_lesson_ids: list[UUID] = Field(default_factory=list)
    child_lesson_ids: list[UUID] = Field(default_factory=list)
    propagation_penalty: float = 0.0
    needs_review: bool = False
    review_reason: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ConflictResponse(BaseModel):
    """Schema for a lesson conflict."""

    id: str
    agent_id: str
    task_context: str
    action_taken: str
    outcome: str
    lesson_text: str
    confidence: float
    conflict_ids: list[str]
    domain: str
    created_at: str


class ConflictListResponse(BaseModel):
    """Response schema for listing conflicts."""

    conflicts: list[ConflictResponse]
    total: int
