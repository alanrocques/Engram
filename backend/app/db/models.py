import uuid
from datetime import datetime
from typing import Literal

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.config import settings


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    pass


class Trace(Base):
    """Raw agent execution traces ingested from OTel or SDK."""

    __tablename__ = "traces"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    agent_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    trace_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    span_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="pending"
    )  # pending, processed, failed
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    # Feature 2: Outcome-routed extraction
    outcome: Mapped[str | None] = mapped_column(String(20), nullable=True)
    extraction_mode: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Feature 3: Provenance tracking
    retrieved_lesson_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=True, default=list
    )
    is_influenced: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (Index("ix_traces_status_created", "status", "created_at"),)


OutcomeType = Literal["success", "failure", "partial"]


class Lesson(Base):
    """Distilled lessons extracted from agent traces."""

    __tablename__ = "lessons"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    agent_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    task_context: Mapped[str] = mapped_column(Text, nullable=False)
    state_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    action_taken: Mapped[str] = mapped_column(Text, nullable=False)
    outcome: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # success, failure, partial
    lesson_text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(
        Vector(settings.embedding_dim), nullable=True
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_validated: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    source_trace_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    domain: Mapped[str] = mapped_column(String(100), nullable=False, default="general")

    # Phase 2: Full-text search
    search_vector: Mapped[str | None] = mapped_column(TSVECTOR, nullable=True)

    # Phase 2: Confidence decay and archival
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Phase 2: Conflict detection
    has_conflict: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    conflict_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )

    # Feature 2: Multi-faceted distillation
    lesson_type: Mapped[str] = mapped_column(String(30), nullable=False, default="general")
    source_trace_ids: Mapped[list[uuid.UUID] | None] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=True
    )
    extraction_mode: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Feature 1: Utility scores (Bellman updates)
    utility: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    retrieval_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Feature 3: Provenance tracking
    parent_lesson_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=True, default=list
    )
    child_lesson_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=True, default=list
    )
    propagation_penalty: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    needs_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    review_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    __table_args__ = (
        Index("ix_lessons_agent_domain", "agent_id", "domain"),
        Index("ix_lessons_confidence", "confidence"),
        Index(
            "ix_lessons_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_lessons_search_vector", "search_vector", postgresql_using="gin"),
        Index("ix_lessons_utility", "utility"),
    )


class LessonRetrieval(Base):
    """Tracks each time a lesson is retrieved and the eventual outcome for utility learning."""

    __tablename__ = "lesson_retrievals"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    lesson_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("lessons.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    trace_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    outcome: Mapped[str | None] = mapped_column(String(20), nullable=True)
    outcome_reported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reward: Mapped[float | None] = mapped_column(Float, nullable=True)
    context_similarity: Mapped[float | None] = mapped_column(Float, nullable=True)


class FailureQueue(Base):
    """Queue of failure traces awaiting batch analysis."""

    __tablename__ = "failure_queue"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    trace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("traces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agent_id: Mapped[str] = mapped_column(String(255), nullable=False)
    error_category: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_signature: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    queued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    batch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ProvenanceEvent(Base):
    """Append-only audit log of provenance events (retrievals, penalties, lesson lineage)."""

    __tablename__ = "provenance_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    event_type: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # retrieval|outcome|penalty_propagated|lesson_extracted|auto_archived
    lesson_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    trace_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    related_lesson_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
