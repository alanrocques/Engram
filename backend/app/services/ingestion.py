import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Lesson, Trace
from app.services.embedding import generate_embedding
from app.services.extraction import extract_lesson_from_trace

logger = logging.getLogger(__name__)


async def process_trace(session: AsyncSession, trace_id: UUID) -> Lesson | None:
    """
    Process a trace to extract a lesson and generate embeddings.

    This is the main ingestion pipeline:
    1. Load the trace
    2. Extract a lesson using Claude
    3. Generate embedding for the lesson
    4. Save the lesson
    5. Update trace status
    """
    # Load the trace
    result = await session.execute(select(Trace).where(Trace.id == trace_id))
    trace = result.scalar_one_or_none()

    if not trace:
        logger.error(f"Trace {trace_id} not found")
        return None

    if trace.status != "pending":
        logger.info(f"Trace {trace_id} already processed (status: {trace.status})")
        return None

    try:
        # Extract lesson from trace using Claude
        lesson_data = await extract_lesson_from_trace(
            trace_data=trace.trace_data,
            agent_id=trace.agent_id,
            trace_id=str(trace.id),
        )

        if not lesson_data:
            logger.warning(f"No lesson extracted from trace {trace_id}")
            await session.execute(
                update(Trace)
                .where(Trace.id == trace_id)
                .values(status="failed", processed_at=datetime.now(timezone.utc))
            )
            return None

        # Generate embedding for the lesson
        embedding_text = f"{lesson_data.task_context} {lesson_data.action_taken} {lesson_data.lesson_text}"
        embedding = generate_embedding(embedding_text)

        # Create the lesson
        lesson = Lesson(
            agent_id=lesson_data.agent_id,
            task_context=lesson_data.task_context,
            state_snapshot=lesson_data.state_snapshot,
            action_taken=lesson_data.action_taken,
            outcome=lesson_data.outcome.value,
            lesson_text=lesson_data.lesson_text,
            embedding=embedding,
            tags=lesson_data.tags,
            source_trace_id=trace.id,
            domain=lesson_data.domain,
        )
        session.add(lesson)

        # Update trace status
        await session.execute(
            update(Trace)
            .where(Trace.id == trace_id)
            .values(status="processed", processed_at=datetime.now(timezone.utc))
        )

        await session.flush()
        await session.refresh(lesson)

        logger.info(f"Successfully processed trace {trace_id} -> lesson {lesson.id}")
        return lesson

    except Exception as e:
        logger.error(f"Error processing trace {trace_id}: {e}")
        await session.execute(
            update(Trace)
            .where(Trace.id == trace_id)
            .values(status="failed", processed_at=datetime.now(timezone.utc))
        )
        raise


async def generate_lesson_embedding(session: AsyncSession, lesson_id: UUID) -> bool:
    """Generate or regenerate embedding for a lesson."""
    result = await session.execute(select(Lesson).where(Lesson.id == lesson_id))
    lesson = result.scalar_one_or_none()

    if not lesson:
        logger.error(f"Lesson {lesson_id} not found")
        return False

    try:
        embedding_text = f"{lesson.task_context} {lesson.action_taken} {lesson.lesson_text}"
        embedding = generate_embedding(embedding_text)

        await session.execute(
            update(Lesson).where(Lesson.id == lesson_id).values(embedding=embedding)
        )

        logger.info(f"Generated embedding for lesson {lesson_id}")
        return True

    except Exception as e:
        logger.error(f"Error generating embedding for lesson {lesson_id}: {e}")
        return False
