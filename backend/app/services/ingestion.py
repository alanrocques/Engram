import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Lesson, Trace
from app.services.embedding import generate_embedding  # used by generate_lesson_embedding below
from app.services.extraction import route_trace_extraction

logger = logging.getLogger(__name__)


def compute_trace_hash(trace_data: dict) -> str:
    """Compute a SHA-256 hash of the trace data for deduplication."""
    # Serialize deterministically
    serialized = json.dumps(trace_data, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode()).hexdigest()


async def check_trace_duplicate(session: AsyncSession, content_hash: str) -> bool:
    """Check if a trace with the same content hash already exists and was processed."""
    result = await session.execute(
        select(Trace.id, Trace.status)
        .where(Trace.content_hash == content_hash)
        .limit(1)
    )
    row = result.first()
    if row and row.status == "processed":
        logger.info(f"Duplicate trace found (hash: {content_hash[:16]}...)")
        return True
    return False


async def process_trace(session: AsyncSession, trace_id: UUID, outcome: str = "unknown") -> Lesson | None:
    """
    Process a trace to extract a lesson and generate embeddings.

    Routes to the appropriate extraction path based on outcome:
      success  → immediate success_pattern lesson
      failure  → classify + queue in failure_queue (no lesson yet)
      partial  → immediate comparative_insight lesson
      unknown  → generic extraction
    """
    result = await session.execute(select(Trace).where(Trace.id == trace_id))
    trace = result.scalar_one_or_none()

    if not trace:
        logger.error(f"Trace {trace_id} not found")
        return None

    if trace.status != "pending":
        logger.info(f"Trace {trace_id} already processed (status: {trace.status})")
        return None

    # Use stored outcome if available, fall back to param
    effective_outcome = trace.outcome or outcome

    try:
        lesson = await route_trace_extraction(session, trace_id, effective_outcome)

        # Mark trace processed regardless of whether a lesson was created
        # (failures queue but don't create a lesson immediately)
        await session.execute(
            update(Trace)
            .where(Trace.id == trace_id)
            .values(
                status="processed",
                processed_at=datetime.now(timezone.utc),
                outcome=effective_outcome,
            )
        )

        if lesson:
            logger.info(f"Successfully processed trace {trace_id} -> lesson {lesson.id}")

            # Trigger async conflict detection for the new lesson
            try:
                from app.workers.tasks import detect_conflicts_task
                detect_conflicts_task.delay(str(lesson.id))
            except Exception as e:
                logger.warning(f"Failed to queue conflict detection for lesson {lesson.id}: {e}")
        else:
            logger.info(f"Trace {trace_id} processed (outcome={effective_outcome}, no immediate lesson)")

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


async def ingest_trace_batch(
    session: AsyncSession,
    traces: list[dict],
    agent_id: str,
) -> dict:
    """
    Ingest a batch of traces with deduplication.

    Args:
        session: Database session
        traces: List of trace data dictionaries
        agent_id: Agent ID for all traces

    Returns:
        Dict with created, skipped (duplicates), and trace IDs
    """
    created_ids = []
    skipped_count = 0

    for trace_data in traces:
        # Compute content hash for deduplication
        content_hash = compute_trace_hash(trace_data)

        # Check for duplicates
        if await check_trace_duplicate(session, content_hash):
            skipped_count += 1
            continue

        # Create the trace
        trace = Trace(
            agent_id=agent_id,
            trace_data=trace_data,
            span_count=len(trace_data.get("spans", [])),
            status="pending",
            content_hash=content_hash,
        )
        session.add(trace)
        await session.flush()
        await session.refresh(trace)
        created_ids.append(str(trace.id))

    await session.commit()

    logger.info(f"Batch ingestion: {len(created_ids)} created, {skipped_count} skipped (duplicates)")

    return {
        "created": len(created_ids),
        "skipped": skipped_count,
        "trace_ids": created_ids,
    }
