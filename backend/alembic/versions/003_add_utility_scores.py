"""Add utility scores and lesson_retrievals table

Revision ID: 003_add_utility_scores
Revises: phase2_intelligence
Create Date: 2026-03-06

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "003_add_utility_scores"
down_revision: Union[str, None] = "phase2_intelligence"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add utility fields to lessons table
    op.add_column("lessons", sa.Column("utility", sa.Float(), nullable=False, server_default="0.5"))
    op.add_column("lessons", sa.Column("retrieval_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("lessons", sa.Column("success_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("lessons", sa.Column("last_retrieved_at", sa.DateTime(timezone=True), nullable=True))

    op.create_index("ix_lessons_utility", "lessons", ["utility"])

    # Create lesson_retrievals table
    op.create_table(
        "lesson_retrievals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("lesson_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("trace_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("outcome", sa.String(20), nullable=True),
        sa.Column("outcome_reported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reward", sa.Float(), nullable=True),
        sa.Column("context_similarity", sa.Float(), nullable=True),
    )

    op.create_index("ix_lesson_retrievals_lesson_id", "lesson_retrievals", ["lesson_id"])
    op.create_index("ix_lesson_retrievals_trace_id", "lesson_retrievals", ["trace_id"])
    # Partial index for pending (outcome IS NULL) lookups
    op.create_index(
        "ix_lesson_retrievals_pending",
        "lesson_retrievals",
        ["trace_id"],
        postgresql_where=sa.text("outcome IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_lesson_retrievals_pending", table_name="lesson_retrievals")
    op.drop_index("ix_lesson_retrievals_trace_id", table_name="lesson_retrievals")
    op.drop_index("ix_lesson_retrievals_lesson_id", table_name="lesson_retrievals")
    op.drop_table("lesson_retrievals")

    op.drop_index("ix_lessons_utility", table_name="lessons")
    op.drop_column("lessons", "last_retrieved_at")
    op.drop_column("lessons", "success_count")
    op.drop_column("lessons", "retrieval_count")
    op.drop_column("lessons", "utility")
