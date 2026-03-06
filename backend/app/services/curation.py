"""Curation service for confidence decay, archival, and conflict detection."""

import logging
import math
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import Lesson

logger = logging.getLogger(__name__)

# Similarity threshold for conflict detection
CONFLICT_SIMILARITY_THRESHOLD = 0.85


async def decay_lesson_confidence(session: AsyncSession) -> dict:
    """
    Apply exponential decay to lesson confidence based on age.

    Uses half-life decay: confidence = initial * (0.5 ^ (age_days / half_life))

    Returns stats about decayed and archived lessons.
    """
    half_life_days = settings.lesson_confidence_half_life_days
    min_threshold = settings.min_confidence_threshold
    now = datetime.now(timezone.utc)

    # Get all non-archived lessons
    result = await session.execute(
        select(Lesson).where(Lesson.is_archived == False)
    )
    lessons = result.scalars().all()

    decayed_count = 0
    archived_count = 0

    for lesson in lessons:
        # Calculate age in days
        created_at = lesson.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)

        age_days = (now - created_at).total_seconds() / 86400

        # Apply exponential decay
        # If lesson was recently validated, use that as the reference point
        if lesson.last_validated:
            last_validated = lesson.last_validated
            if last_validated.tzinfo is None:
                last_validated = last_validated.replace(tzinfo=timezone.utc)
            age_days = (now - last_validated).total_seconds() / 86400

        decay_factor = math.pow(0.5, age_days / half_life_days)
        new_confidence = min(1.0, decay_factor)  # Start from 1.0 and decay

        # Only update if confidence changed significantly
        if abs(lesson.confidence - new_confidence) > 0.01:
            lesson.confidence = new_confidence
            decayed_count += 1

        # Archive if below threshold
        if lesson.confidence < min_threshold:
            lesson.is_archived = True
            archived_count += 1
            logger.info(f"Archived lesson {lesson.id} (confidence: {lesson.confidence:.3f})")

    await session.commit()

    logger.info(f"Confidence decay complete: {decayed_count} decayed, {archived_count} archived")
    return {
        "decayed": decayed_count,
        "archived": archived_count,
        "total_processed": len(lessons),
    }


async def boost_lesson_confidence(
    session: AsyncSession,
    lesson_id: UUID,
    boost_amount: float = 0.1,
) -> float:
    """
    Boost a lesson's confidence after successful validation/use.

    Args:
        session: Database session
        lesson_id: Lesson ID to boost
        boost_amount: Amount to boost (default 0.1)

    Returns:
        New confidence value
    """
    result = await session.execute(select(Lesson).where(Lesson.id == lesson_id))
    lesson = result.scalar_one_or_none()

    if not lesson:
        logger.warning(f"Lesson {lesson_id} not found for confidence boost")
        return 0.0

    new_confidence = min(1.0, lesson.confidence + boost_amount)
    lesson.confidence = new_confidence
    lesson.last_validated = datetime.now(timezone.utc)

    # Unarchive if was archived but now above threshold
    if lesson.is_archived and new_confidence >= settings.min_confidence_threshold:
        lesson.is_archived = False
        logger.info(f"Unarchived lesson {lesson_id} after confidence boost")

    await session.commit()

    logger.info(f"Boosted lesson {lesson_id} confidence to {new_confidence:.3f}")
    return new_confidence


async def detect_conflicts(
    session: AsyncSession,
    lesson_id: UUID,
) -> list[UUID]:
    """
    Detect conflicting lessons for a given lesson.

    A conflict is defined as:
    - High semantic similarity (cosine > 0.85)
    - Opposite outcomes (success vs failure)

    Args:
        session: Database session
        lesson_id: Lesson ID to check for conflicts

    Returns:
        List of conflicting lesson IDs
    """
    result = await session.execute(select(Lesson).where(Lesson.id == lesson_id))
    lesson = result.scalar_one_or_none()

    if not lesson or lesson.embedding is None:
        return []

    # Find lessons with opposite outcome
    opposite_outcomes = {
        "success": "failure",
        "failure": "success",
    }
    opposite_outcome = opposite_outcomes.get(lesson.outcome)

    if not opposite_outcome:
        # "partial" doesn't have a clear opposite
        return []

    # Query for similar lessons with opposite outcome
    similarity = (1 - Lesson.embedding.cosine_distance(lesson.embedding)).label("similarity")

    stmt = (
        select(Lesson.id, similarity)
        .where(
            and_(
                Lesson.id != lesson_id,
                Lesson.outcome == opposite_outcome,
                Lesson.embedding.isnot(None),
                Lesson.is_archived == False,
            )
        )
        .order_by(Lesson.embedding.cosine_distance(lesson.embedding))
        .limit(20)
    )

    result = await session.execute(stmt)
    rows = result.fetchall()

    conflict_ids = []
    for row in rows:
        if row.similarity >= CONFLICT_SIMILARITY_THRESHOLD:
            conflict_ids.append(row.id)

    if conflict_ids:
        # Update the original lesson with conflict info
        lesson.has_conflict = True
        lesson.conflict_ids = conflict_ids

        # Also flag the conflicting lessons
        for conflict_id in conflict_ids:
            await session.execute(
                update(Lesson)
                .where(Lesson.id == conflict_id)
                .values(
                    has_conflict=True,
                    conflict_ids=Lesson.conflict_ids + [lesson_id],
                )
            )

        await session.commit()
        logger.info(f"Detected {len(conflict_ids)} conflicts for lesson {lesson_id}")

    return conflict_ids


async def get_all_conflicts(session: AsyncSession) -> list[dict]:
    """
    Get all lessons that have conflicts.

    Returns a list of conflict groups for review.
    """
    result = await session.execute(
        select(Lesson)
        .where(Lesson.has_conflict == True)
        .order_by(Lesson.created_at.desc())
    )
    lessons = result.scalars().all()

    conflicts = []
    for lesson in lessons:
        conflicts.append({
            "id": str(lesson.id),
            "agent_id": lesson.agent_id,
            "task_context": lesson.task_context,
            "action_taken": lesson.action_taken,
            "outcome": lesson.outcome,
            "lesson_text": lesson.lesson_text,
            "confidence": lesson.confidence,
            "conflict_ids": [str(cid) for cid in lesson.conflict_ids] if lesson.conflict_ids else [],
            "domain": lesson.domain,
            "created_at": lesson.created_at.isoformat(),
        })

    return conflicts
