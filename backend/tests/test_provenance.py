"""Tests for Feature 3: Provenance Tracking."""

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.db.models import Lesson, ProvenanceEvent, Trace
from app.services import provenance as provenance_service

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session
        await session.rollback()
    await engine.dispose()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_trace(db_session, *, outcome="unknown", retrieved_lesson_ids=None) -> Trace:
    trace = Trace(
        agent_id="test-agent",
        trace_data={"action": "test"},
        span_count=1,
        status="processed",
        outcome=outcome,
        retrieved_lesson_ids=retrieved_lesson_ids or [],
        is_influenced=bool(retrieved_lesson_ids),
    )
    db_session.add(trace)
    await db_session.flush()
    await db_session.refresh(trace)
    return trace


async def _create_lesson(db_session, *, utility=0.5) -> Lesson:
    lesson = Lesson(
        agent_id="test-agent",
        task_context="test context",
        state_snapshot={},
        action_taken="test action",
        outcome="success",
        lesson_text="test lesson",
        tags=[],
        domain="general",
        utility=utility,
    )
    db_session.add(lesson)
    await db_session.flush()
    await db_session.refresh(lesson)
    return lesson


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_record_trace_context(db_session):
    """record_trace_context updates trace fields and logs provenance events."""
    lesson = await _create_lesson(db_session)
    trace = await _create_trace(db_session)

    await provenance_service.record_trace_context(
        session=db_session,
        trace_id=trace.id,
        retrieved_lesson_ids=[lesson.id],
    )
    await db_session.flush()

    # Check trace updated
    result = await db_session.execute(select(Trace).where(Trace.id == trace.id))
    updated_trace = result.scalar_one()
    assert updated_trace.is_influenced is True
    assert lesson.id in (updated_trace.retrieved_lesson_ids or [])

    # Check provenance event logged
    result = await db_session.execute(
        select(ProvenanceEvent).where(
            ProvenanceEvent.trace_id == trace.id,
            ProvenanceEvent.event_type == "retrieval",
        )
    )
    events = result.scalars().all()
    assert len(events) == 1
    assert events[0].lesson_id == lesson.id


async def test_on_lesson_extracted_sets_parent_ids(db_session):
    """on_lesson_extracted links parent and child lessons correctly."""
    parent = await _create_lesson(db_session)
    # Create trace with parent in context
    trace = await _create_trace(db_session, retrieved_lesson_ids=[parent.id])

    child = await _create_lesson(db_session)

    await provenance_service.on_lesson_extracted(
        session=db_session,
        new_lesson_id=child.id,
        source_trace_id=trace.id,
    )
    await db_session.flush()

    # Child has parent_lesson_ids set
    result = await db_session.execute(select(Lesson).where(Lesson.id == child.id))
    updated_child = result.scalar_one()
    assert parent.id in (updated_child.parent_lesson_ids or [])

    # Parent has child_lesson_ids updated
    result = await db_session.execute(select(Lesson).where(Lesson.id == parent.id))
    updated_parent = result.scalar_one()
    assert child.id in (updated_parent.child_lesson_ids or [])


async def test_direct_penalty_applied(db_session):
    """Lesson used in a failing trace gets utility decreased and propagation_penalty > 0."""
    lesson = await _create_lesson(db_session, utility=0.6)
    trace = await _create_trace(db_session, retrieved_lesson_ids=[lesson.id])

    await provenance_service.propagate_failure_penalty(session=db_session, trace_id=trace.id)
    await db_session.flush()

    result = await db_session.execute(select(Lesson).where(Lesson.id == lesson.id))
    updated = result.scalar_one()
    assert updated.utility < 0.6
    assert updated.propagation_penalty > 0


async def test_decayed_propagation_to_grandparent(db_session):
    """Grandparent lesson receives a decayed penalty (penalty * PROPAGATION_DECAY)."""
    grandparent = await _create_lesson(db_session, utility=0.8)
    parent = await _create_lesson(db_session, utility=0.7)

    # Wire up: grandparent is parent of parent
    from sqlalchemy import update
    await db_session.execute(
        update(Lesson)
        .where(Lesson.id == parent.id)
        .values(parent_lesson_ids=[grandparent.id])
    )
    await db_session.flush()

    # Trace uses parent in context
    trace = await _create_trace(db_session, retrieved_lesson_ids=[parent.id])

    await provenance_service.propagate_failure_penalty(session=db_session, trace_id=trace.id)
    await db_session.flush()

    result = await db_session.execute(select(Lesson).where(Lesson.id == grandparent.id))
    updated_gp = result.scalar_one()
    result2 = await db_session.execute(select(Lesson).where(Lesson.id == parent.id))
    updated_parent = result2.scalar_one()

    # Grandparent penalty is half of parent penalty (PROPAGATION_DECAY=0.5)
    assert updated_gp.propagation_penalty > 0
    assert updated_gp.propagation_penalty < updated_parent.propagation_penalty


async def test_max_depth_respected(db_session):
    """Penalty does not propagate beyond MAX_PROPAGATION_DEPTH=3 hops."""
    from sqlalchemy import update

    # Create a 5-level chain: l0 → l1 → l2 → l3 → l4
    lessons = []
    for _ in range(5):
        l = await _create_lesson(db_session, utility=0.8)
        lessons.append(l)

    for i in range(1, 5):
        await db_session.execute(
            update(Lesson)
            .where(Lesson.id == lessons[i].id)
            .values(parent_lesson_ids=[lessons[i - 1].id])
        )
    await db_session.flush()

    # Trace uses lessons[4] (the deepest child) in context
    trace = await _create_trace(db_session, retrieved_lesson_ids=[lessons[4].id])
    await provenance_service.propagate_failure_penalty(session=db_session, trace_id=trace.id)
    await db_session.flush()

    # lessons[4]: depth 0 — penalized
    # lessons[3]: depth 1 — penalized
    # lessons[2]: depth 2 — penalized
    # lessons[1]: depth 3 = MAX_PROPAGATION_DEPTH — NOT penalized (boundary is exclusive)
    # lessons[0]: depth 4 — NOT penalized

    for i in range(5):
        result = await db_session.execute(select(Lesson).where(Lesson.id == lessons[i].id))
        l = result.scalar_one()
        if i >= 2:  # lessons[4], [3], [2] get penalized (depths 0, 1, 2)
            assert l.propagation_penalty > 0, f"lessons[{i}] should be penalized"
        else:  # lessons[1], [0] at depth >= 3 should NOT be penalized
            assert l.propagation_penalty == 0.0, f"lessons[{i}] should NOT be penalized"


async def test_needs_review_flagged_when_penalty_exceeds_threshold(db_session):
    """Lesson with accumulated penalty > REVIEW_PENALTY_THRESHOLD gets needs_review=True."""
    # Start with existing penalty near threshold
    from sqlalchemy import update

    lesson = await _create_lesson(db_session, utility=0.6)
    # Pre-set propagation_penalty just below threshold
    await db_session.execute(
        update(Lesson)
        .where(Lesson.id == lesson.id)
        .values(propagation_penalty=0.25)  # threshold is 0.3, adding 0.15 pushes it over
    )
    await db_session.flush()

    trace = await _create_trace(db_session, retrieved_lesson_ids=[lesson.id])
    await provenance_service.propagate_failure_penalty(session=db_session, trace_id=trace.id)
    await db_session.flush()

    result = await db_session.execute(select(Lesson).where(Lesson.id == lesson.id))
    updated = result.scalar_one()
    assert updated.propagation_penalty > 0.3
    assert updated.needs_review is True
    assert updated.review_reason is not None


async def test_no_penalty_for_empty_context(db_session):
    """Failing trace with no retrieved_lesson_ids → no provenance changes."""
    lesson = await _create_lesson(db_session, utility=0.7)
    trace = await _create_trace(db_session, retrieved_lesson_ids=[])

    await provenance_service.propagate_failure_penalty(session=db_session, trace_id=trace.id)
    await db_session.flush()

    result = await db_session.execute(select(Lesson).where(Lesson.id == lesson.id))
    unchanged = result.scalar_one()
    assert unchanged.utility == pytest.approx(0.7)
    assert unchanged.propagation_penalty == 0.0


async def test_cleanup_toxic_lessons(db_session):
    """Lessons meeting toxic criteria get archived by cleanup task logic."""
    from sqlalchemy import update

    lesson = await _create_lesson(db_session, utility=0.1)
    await db_session.execute(
        update(Lesson)
        .where(Lesson.id == lesson.id)
        .values(
            propagation_penalty=0.6,
            retrieval_count=10,
            is_archived=False,
        )
    )
    await db_session.flush()

    # Simulate cleanup task inline
    result = await db_session.execute(
        select(Lesson.id).where(
            Lesson.propagation_penalty > 0.5,
            Lesson.utility < 0.15,
            Lesson.retrieval_count > 5,
            Lesson.is_archived == False,  # noqa: E712
        )
    )
    ids = [row[0] for row in result.all()]
    assert lesson.id in ids

    await db_session.execute(
        update(Lesson).where(Lesson.id.in_(ids)).values(is_archived=True)
    )
    for lid in ids:
        db_session.add(ProvenanceEvent(
            event_type="auto_archived",
            lesson_id=lid,
            payload={"reason": "toxic: high penalty + low utility"},
        ))
    await db_session.flush()

    result = await db_session.execute(select(Lesson).where(Lesson.id == lesson.id))
    archived = result.scalar_one()
    assert archived.is_archived is True


async def test_get_lesson_provenance_returns_full_record(db_session):
    """get_lesson_provenance returns all expected fields."""
    lesson = await _create_lesson(db_session)
    trace = await _create_trace(db_session)

    # Add a provenance event
    db_session.add(ProvenanceEvent(
        event_type="retrieval",
        lesson_id=lesson.id,
        trace_id=trace.id,
        payload={"test": True},
    ))
    await db_session.flush()

    provenance = await provenance_service.get_lesson_provenance(db_session, lesson.id)

    assert provenance["lesson_id"] == str(lesson.id)
    assert "parent_lesson_ids" in provenance
    assert "child_lesson_ids" in provenance
    assert "propagation_penalty" in provenance
    assert "needs_review" in provenance
    assert "retrieval_history" in provenance
    assert "provenance_events" in provenance
    assert len(provenance["provenance_events"]) >= 1
    assert provenance["provenance_events"][0]["event_type"] == "retrieval"
