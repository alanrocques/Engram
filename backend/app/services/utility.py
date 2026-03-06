"""Utility score service — Bellman EMA updates for lesson effectiveness tracking."""

import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Lesson, LessonRetrieval

logger = logging.getLogger(__name__)

LEARNING_RATE = 0.15
DISCOUNT_FACTOR = 0.9
UTILITY_MIN = 0.05
UTILITY_MAX = 0.98

REWARD_MAP = {"success": 1.0, "failure": 0.0, "partial": 0.5}


async def record_retrieval(
    session: AsyncSession,
    lesson_id: UUID,
    trace_id: UUID | None,
    context_similarity: float = 1.0,
) -> LessonRetrieval:
    """
    Record that a lesson was retrieved for a given trace.

    Creates a lesson_retrievals row with outcome=NULL (pending) and increments
    the lesson's retrieval_count + last_retrieved_at.
    """
    retrieval = LessonRetrieval(
        lesson_id=lesson_id,
        trace_id=trace_id,
        context_similarity=context_similarity,
    )
    session.add(retrieval)

    await session.execute(
        update(Lesson)
        .where(Lesson.id == lesson_id)
        .values(
            retrieval_count=Lesson.retrieval_count + 1,
            last_retrieved_at=datetime.now(timezone.utc),
        )
    )

    await session.flush()
    await session.refresh(retrieval)
    return retrieval


async def report_outcome(
    session: AsyncSession,
    trace_id: UUID,
    outcome: str,
    downstream_utility: float = 0.0,
) -> list[UUID]:
    """
    Report the outcome for a trace and update utility on all lessons retrieved during it.

    Uses EMA Bellman update:
        td_target = reward + DISCOUNT_FACTOR * downstream_utility
        new_utility = (1 - LR) * old_utility + LR * td_target

    Returns list of lesson IDs whose utility was updated.
    """
    reward = REWARD_MAP.get(outcome.lower(), 0.5)
    td_target = reward + DISCOUNT_FACTOR * downstream_utility
    now = datetime.now(timezone.utc)

    # Find all pending retrievals for this trace
    result = await session.execute(
        select(LessonRetrieval)
        .where(
            and_(
                LessonRetrieval.trace_id == trace_id,
                LessonRetrieval.outcome.is_(None),
            )
        )
    )
    pending = result.scalars().all()

    if not pending:
        logger.debug(f"No pending retrievals for trace {trace_id}")
        return []

    updated_lesson_ids: list[UUID] = []

    for retrieval in pending:
        # Load current lesson utility
        lesson_result = await session.execute(
            select(Lesson.utility).where(Lesson.id == retrieval.lesson_id)
        )
        row = lesson_result.first()
        if row is None:
            continue

        old_utility = row.utility
        new_utility = (1.0 - LEARNING_RATE) * old_utility + LEARNING_RATE * td_target
        new_utility = max(UTILITY_MIN, min(UTILITY_MAX, new_utility))

        # Update retrieval record
        retrieval.outcome = outcome
        retrieval.outcome_reported_at = now
        retrieval.reward = reward

        # Update lesson utility (and success_count if success)
        update_vals: dict = {"utility": new_utility}
        if outcome.lower() == "success":
            update_vals["success_count"] = Lesson.success_count + 1

        await session.execute(
            update(Lesson).where(Lesson.id == retrieval.lesson_id).values(**update_vals)
        )

        updated_lesson_ids.append(retrieval.lesson_id)
        logger.debug(
            f"Lesson {retrieval.lesson_id}: utility {old_utility:.3f} → {new_utility:.3f} "
            f"(outcome={outcome}, reward={reward:.1f})"
        )

    await session.flush()
    logger.info(f"Updated utility for {len(updated_lesson_ids)} lessons (trace {trace_id})")
    return updated_lesson_ids
