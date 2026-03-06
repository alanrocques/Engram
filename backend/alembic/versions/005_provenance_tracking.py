"""Provenance tracking: trace context, lesson lineage, failure penalty propagation

Revision ID: 005_provenance_tracking
Revises: 004_multi_faceted_distillation
Create Date: 2026-03-06

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "005_provenance_tracking"
down_revision: Union[str, None] = "004_multi_faceted_distillation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # traces table additions
    op.add_column(
        "traces",
        sa.Column(
            "retrieved_lesson_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=True,
            server_default="{}",
        ),
    )
    op.add_column(
        "traces",
        sa.Column("is_influenced", sa.Boolean(), nullable=False, server_default="FALSE"),
    )

    # lessons table additions
    op.add_column(
        "lessons",
        sa.Column(
            "parent_lesson_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=True,
            server_default="{}",
        ),
    )
    op.add_column(
        "lessons",
        sa.Column(
            "child_lesson_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=True,
            server_default="{}",
        ),
    )
    op.add_column(
        "lessons",
        sa.Column("propagation_penalty", sa.Float(), nullable=False, server_default="0.0"),
    )
    op.add_column(
        "lessons",
        sa.Column("needs_review", sa.Boolean(), nullable=False, server_default="FALSE"),
    )
    op.add_column(
        "lessons",
        sa.Column("review_reason", sa.String(255), nullable=True),
    )

    # provenance_events table (append-only audit log)
    op.create_table(
        "provenance_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("event_type", sa.String(30), nullable=False),
        sa.Column("lesson_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("trace_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("related_lesson_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index("ix_provenance_lesson_id", "provenance_events", ["lesson_id"])
    op.create_index("ix_provenance_trace_id", "provenance_events", ["trace_id"])
    op.create_index("ix_provenance_event_type", "provenance_events", ["event_type"])
    op.create_index("ix_lessons_needs_review", "lessons", ["needs_review"])


def downgrade() -> None:
    op.drop_index("ix_lessons_needs_review", table_name="lessons")
    op.drop_index("ix_provenance_event_type", table_name="provenance_events")
    op.drop_index("ix_provenance_trace_id", table_name="provenance_events")
    op.drop_index("ix_provenance_lesson_id", table_name="provenance_events")
    op.drop_table("provenance_events")

    op.drop_column("lessons", "review_reason")
    op.drop_column("lessons", "needs_review")
    op.drop_column("lessons", "propagation_penalty")
    op.drop_column("lessons", "child_lesson_ids")
    op.drop_column("lessons", "parent_lesson_ids")

    op.drop_column("traces", "is_influenced")
    op.drop_column("traces", "retrieved_lesson_ids")
