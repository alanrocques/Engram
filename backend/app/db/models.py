import uuid
from datetime import datetime
from typing import Literal

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
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
    )
