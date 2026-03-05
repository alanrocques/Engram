from pydantic import BaseModel, ConfigDict, Field


class RetrieveRequest(BaseModel):
    """Request schema for retrieving relevant lessons."""

    query: str = Field(..., min_length=1, description="The context or question to find relevant lessons for")
    agent_id: str | None = Field(default=None, description="Filter lessons by agent ID")
    domain: str | None = Field(default=None, description="Filter lessons by domain")
    top_k: int = Field(default=5, ge=1, le=50, description="Number of lessons to retrieve")
    min_confidence: float = Field(default=0.3, ge=0.0, le=1.0, description="Minimum confidence threshold")
    include_context: bool = Field(default=True, description="Include formatted context string")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "query": "How should I handle a customer refund request?",
                "agent_id": "support-bot-v2",
                "domain": "support",
                "top_k": 5,
                "min_confidence": 0.3,
                "include_context": True,
            }
        }
    )


class RetrievedLesson(BaseModel):
    """A single retrieved lesson with similarity score."""

    id: str
    agent_id: str
    task_context: str
    action_taken: str
    outcome: str
    lesson_text: str
    confidence: float
    tags: list[str]
    domain: str
    similarity: float


class RetrieveResponse(BaseModel):
    """Response schema for lesson retrieval."""

    lessons: list[RetrievedLesson]
    context: str | None = Field(default=None, description="Formatted context for agent prompt")
    total: int = Field(..., description="Total number of lessons returned")
