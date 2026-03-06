"""Provenance tracking service — records lesson lineage and propagates failure penalties."""

import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Lesson, LessonRetrieval, ProvenanceEvent, Trace

logger = logging.getLogger(__name__)

FAILURE_PENALTY = 0.15
PROPAGATION_DECAY = 0.5
MAX_PROPAGATION_DEPTH = 3
REVIEW_PENALTY_THRESHOLD = 0.3


async def record_trace_context(
    session: AsyncSession,
    trace_id: UUID,
    retrieved_lesson_ids: list[UUID],
) -> None:
    """
    Record which lessons were in context when a trace was executed.

    Updates trace.retrieved_lesson_ids and trace.is_influenced, and logs a
    provenance_event per lesson.
    """
    if not retrieved_lesson_ids:
        return

    await session.execute(
        update(Trace)
        .where(Trace.id == trace_id)
        .values(
            retrieved_lesson_ids=retrieved_lesson_ids,
            is_influenced=True,
        )
    )

    for lesson_id in retrieved_lesson_ids:
        event = ProvenanceEvent(
            event_type="retrieval",
            lesson_id=lesson_id,
            trace_id=trace_id,
            payload={"trace_id": str(trace_id)},
        )
        session.add(event)

    await session.flush()
    logger.info(f"Recorded context for trace {trace_id}: {len(retrieved_lesson_ids)} lessons")


async def on_lesson_extracted(
    session: AsyncSession,
    new_lesson_id: UUID,
    source_trace_id: UUID,
) -> None:
    """
    Link a newly extracted lesson to the lessons that were in context during its source trace.

    Sets parent_lesson_ids on the new lesson and appends to child_lesson_ids on each parent.
    """
    result = await session.execute(
        select(Trace.retrieved_lesson_ids).where(Trace.id == source_trace_id)
    )
    row = result.first()
    if not row or not row[0]:
        return

    parent_ids = list(row[0])
    if not parent_ids:
        return

    # Set parent_lesson_ids on new lesson
    await session.execute(
        update(Lesson)
        .where(Lesson.id == new_lesson_id)
        .values(parent_lesson_ids=parent_ids)
    )

    # Append new_lesson_id to each parent's child_lesson_ids
    for parent_id in parent_ids:
        parent_result = await session.execute(
            select(Lesson.child_lesson_ids).where(Lesson.id == parent_id)
        )
        parent_row = parent_result.first()
        if parent_row is not None:
            existing = list(parent_row[0] or [])
            if new_lesson_id not in existing:
                existing.append(new_lesson_id)
                await session.execute(
                    update(Lesson)
                    .where(Lesson.id == parent_id)
                    .values(child_lesson_ids=existing)
                )

    # Log provenance event
    event = ProvenanceEvent(
        event_type="lesson_extracted",
        lesson_id=new_lesson_id,
        trace_id=source_trace_id,
        payload={"parent_lesson_ids": [str(p) for p in parent_ids]},
    )
    session.add(event)
    await session.flush()
    logger.info(f"Linked lesson {new_lesson_id} to {len(parent_ids)} parents via trace {source_trace_id}")


async def propagate_failure_penalty(
    session: AsyncSession,
    trace_id: UUID,
) -> None:
    """
    Apply failure penalties to lessons that were in context during a failed trace,
    then recursively propagate decayed penalties up to MAX_PROPAGATION_DEPTH hops.
    """
    result = await session.execute(
        select(Trace.retrieved_lesson_ids).where(Trace.id == trace_id)
    )
    row = result.first()
    if not row or not row[0]:
        return

    direct_lesson_ids = list(row[0])
    if not direct_lesson_ids:
        return

    await _apply_penalty_to_lessons(
        session, direct_lesson_ids, FAILURE_PENALTY, trace_id, depth=0
    )
    logger.info(f"Propagated failure penalty from trace {trace_id} to {len(direct_lesson_ids)} lessons")


async def _apply_penalty_to_lessons(
    session: AsyncSession,
    lesson_ids: list[UUID],
    penalty: float,
    trace_id: UUID,
    depth: int,
) -> None:
    """Recursively apply penalty to lessons and walk up parent chains."""
    if depth >= MAX_PROPAGATION_DEPTH or not lesson_ids or penalty < 0.001:
        return

    for lesson_id in lesson_ids:
        result = await session.execute(
            select(Lesson.utility, Lesson.propagation_penalty, Lesson.parent_lesson_ids)
            .where(Lesson.id == lesson_id)
        )
        row = result.first()
        if row is None:
            continue

        current_utility, current_penalty, parent_ids = row[0], row[1], row[2] or []

        new_utility = max(0.05, current_utility - penalty)
        new_penalty = current_penalty + penalty
        needs_review = new_penalty > REVIEW_PENALTY_THRESHOLD
        review_reason = (
            f"Accumulated propagation penalty {new_penalty:.3f} > {REVIEW_PENALTY_THRESHOLD}"
            if needs_review
            else None
        )

        update_vals: dict = {
            "utility": new_utility,
            "propagation_penalty": new_penalty,
        }
        if needs_review:
            update_vals["needs_review"] = True
            update_vals["review_reason"] = review_reason

        await session.execute(
            update(Lesson).where(Lesson.id == lesson_id).values(**update_vals)
        )

        event = ProvenanceEvent(
            event_type="penalty_propagated",
            lesson_id=lesson_id,
            trace_id=trace_id,
            payload={
                "penalty_applied": penalty,
                "depth": depth,
                "new_utility": new_utility,
                "new_propagation_penalty": new_penalty,
            },
        )
        session.add(event)

        # Recurse to parents with decayed penalty
        if parent_ids and depth + 1 < MAX_PROPAGATION_DEPTH:
            decayed = penalty * PROPAGATION_DECAY
            await _apply_penalty_to_lessons(
                session, list(parent_ids), decayed, trace_id, depth + 1
            )

    await session.flush()


async def get_lesson_provenance(session: AsyncSession, lesson_id: UUID) -> dict:
    """
    Return the full provenance record for a lesson: parents, children, penalty,
    retrieval history, and provenance events.
    """
    result = await session.execute(
        select(
            Lesson.id,
            Lesson.parent_lesson_ids,
            Lesson.child_lesson_ids,
            Lesson.propagation_penalty,
            Lesson.needs_review,
            Lesson.review_reason,
        ).where(Lesson.id == lesson_id)
    )
    row = result.first()
    if row is None:
        return {}

    # Retrieval history
    retrievals_result = await session.execute(
        select(
            LessonRetrieval.id,
            LessonRetrieval.trace_id,
            LessonRetrieval.retrieved_at,
            LessonRetrieval.outcome,
            LessonRetrieval.reward,
        ).where(LessonRetrieval.lesson_id == lesson_id)
        .order_by(LessonRetrieval.retrieved_at.desc())
        .limit(20)
    )
    retrievals = [
        {
            "id": str(r[0]),
            "trace_id": str(r[1]) if r[1] else None,
            "retrieved_at": r[2].isoformat() if r[2] else None,
            "outcome": r[3],
            "reward": r[4],
        }
        for r in retrievals_result.all()
    ]

    # Provenance events
    events_result = await session.execute(
        select(
            ProvenanceEvent.id,
            ProvenanceEvent.event_type,
            ProvenanceEvent.trace_id,
            ProvenanceEvent.related_lesson_id,
            ProvenanceEvent.payload,
            ProvenanceEvent.created_at,
        ).where(ProvenanceEvent.lesson_id == lesson_id)
        .order_by(ProvenanceEvent.created_at.desc())
        .limit(50)
    )
    events = [
        {
            "id": str(e[0]),
            "event_type": e[1],
            "trace_id": str(e[2]) if e[2] else None,
            "related_lesson_id": str(e[3]) if e[3] else None,
            "payload": e[4],
            "created_at": e[5].isoformat() if e[5] else None,
        }
        for e in events_result.all()
    ]

    return {
        "lesson_id": str(row[0]),
        "parent_lesson_ids": [str(p) for p in (row[1] or [])],
        "child_lesson_ids": [str(c) for c in (row[2] or [])],
        "propagation_penalty": row[3],
        "needs_review": row[4],
        "review_reason": row[5],
        "retrieval_history": retrievals,
        "provenance_events": events,
    }
