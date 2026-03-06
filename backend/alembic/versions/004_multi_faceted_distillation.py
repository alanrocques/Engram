"""Multi-faceted distillation: outcome routing, failure queue, lesson types

Revision ID: 004_multi_faceted_distillation
Revises: 003_add_utility_scores
Create Date: 2026-03-06

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "004_multi_faceted_distillation"
down_revision: Union[str, None] = "003_add_utility_scores"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # traces table additions
    op.add_column("traces", sa.Column("outcome", sa.String(20), nullable=True))
    op.add_column("traces", sa.Column("extraction_mode", sa.String(20), nullable=True))

    # lessons table additions
    op.add_column(
        "lessons",
        sa.Column("lesson_type", sa.String(30), nullable=False, server_default="general"),
    )
    op.add_column("lessons", sa.Column("source_trace_ids", postgresql.ARRAY(postgresql.UUID()), nullable=True))
    op.add_column("lessons", sa.Column("extraction_mode", sa.String(20), nullable=True))

    op.create_index("ix_lessons_lesson_type", "lessons", ["lesson_type"])

    # failure_queue table
    op.create_table(
        "failure_queue",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "trace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("traces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("agent_id", sa.String(255), nullable=False),
        sa.Column("error_category", sa.String(255), nullable=True),
        sa.Column("error_signature", sa.String(512), nullable=True),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index("ix_failure_queue_trace_id", "failure_queue", ["trace_id"])
    op.create_index("ix_failure_queue_error_signature", "failure_queue", ["error_signature"])
    op.create_index(
        "ix_failure_queue_unprocessed",
        "failure_queue",
        ["queued_at"],
        postgresql_where=sa.text("processed_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_failure_queue_unprocessed", table_name="failure_queue")
    op.drop_index("ix_failure_queue_error_signature", table_name="failure_queue")
    op.drop_index("ix_failure_queue_trace_id", table_name="failure_queue")
    op.drop_table("failure_queue")

    op.drop_index("ix_lessons_lesson_type", table_name="lessons")
    op.drop_column("lessons", "extraction_mode")
    op.drop_column("lessons", "source_trace_ids")
    op.drop_column("lessons", "lesson_type")

    op.drop_column("traces", "extraction_mode")
    op.drop_column("traces", "outcome")
