"""Phase 2: Intelligence - hybrid search, confidence decay, conflict detection, batch dedup

Revision ID: phase2_intelligence
Revises: 8ef2ebd56eb6
Create Date: 2026-03-05

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'phase2_intelligence'
down_revision: Union[str, None] = '8ef2ebd56eb6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add search_vector column for full-text search (generated from lesson_text + task_context)
    op.add_column('lessons', sa.Column('search_vector', postgresql.TSVECTOR(), nullable=True))

    # Add confidence decay and archival fields
    op.add_column('lessons', sa.Column('is_archived', sa.Boolean(), nullable=False, server_default='false'))

    # Add conflict detection fields
    op.add_column('lessons', sa.Column('has_conflict', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('lessons', sa.Column('conflict_ids', postgresql.ARRAY(sa.UUID()), nullable=False, server_default='{}'))

    # Add content hash for deduplication
    op.add_column('traces', sa.Column('content_hash', sa.String(64), nullable=True))

    # Create GIN index for full-text search
    op.create_index('ix_lessons_search_vector', 'lessons', ['search_vector'], unique=False, postgresql_using='gin')

    # Create index for archived status (partial index for non-archived)
    op.create_index('ix_lessons_not_archived', 'lessons', ['is_archived'], unique=False, postgresql_where=sa.text('is_archived = false'))

    # Create index for conflicts
    op.create_index('ix_lessons_has_conflict', 'lessons', ['has_conflict'], unique=False, postgresql_where=sa.text('has_conflict = true'))

    # Create index for content hash deduplication
    op.create_index('ix_traces_content_hash', 'traces', ['content_hash'], unique=False)

    # Populate search_vector for existing lessons
    op.execute("""
        UPDATE lessons
        SET search_vector = to_tsvector('english', coalesce(task_context, '') || ' ' || coalesce(lesson_text, '') || ' ' || coalesce(action_taken, ''))
    """)

    # Create trigger to auto-update search_vector on insert/update
    op.execute("""
        CREATE OR REPLACE FUNCTION lessons_search_vector_trigger() RETURNS trigger AS $$
        BEGIN
            NEW.search_vector := to_tsvector('english', coalesce(NEW.task_context, '') || ' ' || coalesce(NEW.lesson_text, '') || ' ' || coalesce(NEW.action_taken, ''));
            RETURN NEW;
        END
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER lessons_search_vector_update
        BEFORE INSERT OR UPDATE ON lessons
        FOR EACH ROW EXECUTE FUNCTION lessons_search_vector_trigger();
    """)


def downgrade() -> None:
    # Drop trigger and function
    op.execute("DROP TRIGGER IF EXISTS lessons_search_vector_update ON lessons")
    op.execute("DROP FUNCTION IF EXISTS lessons_search_vector_trigger()")

    # Drop indexes
    op.drop_index('ix_traces_content_hash', table_name='traces')
    op.drop_index('ix_lessons_has_conflict', table_name='lessons')
    op.drop_index('ix_lessons_not_archived', table_name='lessons')
    op.drop_index('ix_lessons_search_vector', table_name='lessons')

    # Drop columns
    op.drop_column('traces', 'content_hash')
    op.drop_column('lessons', 'conflict_ids')
    op.drop_column('lessons', 'has_conflict')
    op.drop_column('lessons', 'is_archived')
    op.drop_column('lessons', 'search_vector')
