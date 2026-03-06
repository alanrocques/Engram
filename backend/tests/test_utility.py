"""Tests for Feature 1: Utility Scores via Bellman Updates."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.db.models import Lesson, LessonRetrieval
from app.services import utility as utility_service


# ---------------------------------------------------------------------------
# Session fixture (direct DB access, not via HTTP)
# ---------------------------------------------------------------------------

@pytest.fixture
async def db_session():
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def create_lesson(session: AsyncSession, **kwargs) -> Lesson:
    defaults = dict(
        agent_id="test-agent",
        task_context="test context",
        action_taken="test action",
        outcome="success",
        lesson_text="test lesson",
        tags=[],
        domain="testing",
        utility=0.5,
        retrieval_count=0,
        success_count=0,
    )
    defaults.update(kwargs)
    lesson = Lesson(**defaults)
    session.add(lesson)
    await session.flush()
    await session.refresh(lesson)
    return lesson


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_utility_increases_on_success(db_session: AsyncSession):
    """Utility increases when outcome is success."""
    lesson = await create_lesson(db_session, utility=0.5)
    trace_id = uuid.uuid4()

    await utility_service.record_retrieval(db_session, lesson.id, trace_id)
    await utility_service.report_outcome(db_session, trace_id, "success")

    await db_session.refresh(lesson)
    assert lesson.utility > 0.5


@pytest.mark.asyncio
async def test_utility_decreases_on_failure(db_session: AsyncSession):
    """Utility decreases when outcome is failure."""
    lesson = await create_lesson(db_session, utility=0.5)
    trace_id = uuid.uuid4()

    await utility_service.record_retrieval(db_session, lesson.id, trace_id)
    await utility_service.report_outcome(db_session, trace_id, "failure")

    await db_session.refresh(lesson)
    assert lesson.utility < 0.5


@pytest.mark.asyncio
async def test_utility_clamps_at_max(db_session: AsyncSession):
    """Utility never exceeds UTILITY_MAX after many successes."""
    lesson = await create_lesson(db_session, utility=0.97)

    for _ in range(10):
        trace_id = uuid.uuid4()
        await utility_service.record_retrieval(db_session, lesson.id, trace_id)
        await utility_service.report_outcome(db_session, trace_id, "success")
        await db_session.refresh(lesson)

    assert lesson.utility <= utility_service.UTILITY_MAX


@pytest.mark.asyncio
async def test_utility_clamps_at_min(db_session: AsyncSession):
    """Utility never goes below UTILITY_MIN after many failures."""
    lesson = await create_lesson(db_session, utility=0.06)

    for _ in range(10):
        trace_id = uuid.uuid4()
        await utility_service.record_retrieval(db_session, lesson.id, trace_id)
        await utility_service.report_outcome(db_session, trace_id, "failure")
        await db_session.refresh(lesson)

    assert lesson.utility >= utility_service.UTILITY_MIN


@pytest.mark.asyncio
async def test_retrieval_count_increments(db_session: AsyncSession):
    """retrieval_count increments each time record_retrieval is called."""
    lesson = await create_lesson(db_session)

    await utility_service.record_retrieval(db_session, lesson.id, uuid.uuid4())
    await utility_service.record_retrieval(db_session, lesson.id, uuid.uuid4())
    await db_session.refresh(lesson)

    assert lesson.retrieval_count == 2


@pytest.mark.asyncio
async def test_success_count_increments(db_session: AsyncSession):
    """success_count increments only on success outcomes."""
    lesson = await create_lesson(db_session)
    trace_id = uuid.uuid4()

    await utility_service.record_retrieval(db_session, lesson.id, trace_id)
    await utility_service.report_outcome(db_session, trace_id, "success")
    await db_session.refresh(lesson)

    assert lesson.success_count == 1

    trace_id2 = uuid.uuid4()
    await utility_service.record_retrieval(db_session, lesson.id, trace_id2)
    await utility_service.report_outcome(db_session, trace_id2, "failure")
    await db_session.refresh(lesson)

    assert lesson.success_count == 1  # unchanged on failure


@pytest.mark.asyncio
async def test_report_outcome_no_pending_is_noop(db_session: AsyncSession):
    """report_outcome returns empty list when no pending retrievals exist."""
    lesson = await create_lesson(db_session)
    result = await utility_service.report_outcome(db_session, uuid.uuid4(), "success")
    assert result == []
    await db_session.refresh(lesson)
    assert lesson.utility == 0.5  # unchanged


@pytest.mark.asyncio
async def test_utility_converges_alternating(db_session: AsyncSession):
    """Utility stays near 0.5 with alternating success/failure over 5 cycles."""
    lesson = await create_lesson(db_session, utility=0.5)

    for i in range(5):
        outcome = "success" if i % 2 == 0 else "failure"
        trace_id = uuid.uuid4()
        await utility_service.record_retrieval(db_session, lesson.id, trace_id)
        await utility_service.report_outcome(db_session, trace_id, outcome)
        await db_session.refresh(lesson)

    # After alternating, utility should stay in a reasonable range around 0.5
    assert 0.2 <= lesson.utility <= 0.8


@pytest.mark.asyncio
async def test_high_utility_lesson_ranks_higher(client: AsyncClient):
    """A lesson with high utility ranks above a low-utility one when utility_weight=1."""
    # Create two lessons with different utilities via the API
    resp1 = await client.post("/api/v1/lessons", json={
        "agent_id": "rank-test",
        "task_context": "handle database connection timeout",
        "action_taken": "retry with exponential backoff",
        "outcome": "success",
        "lesson_text": "Use exponential backoff for database timeouts",
        "domain": "testing",
    })
    assert resp1.status_code == 201
    lesson1_id = resp1.json()["id"]

    resp2 = await client.post("/api/v1/lessons", json={
        "agent_id": "rank-test",
        "task_context": "handle database connection timeout error retry",
        "action_taken": "retry immediately without delay",
        "outcome": "failure",
        "lesson_text": "Immediate retry without backoff causes cascading failures on timeouts",
        "domain": "testing",
    })
    assert resp2.status_code == 201
    lesson2_id = resp2.json()["id"]

    # Report success for lesson1 several times to boost its utility
    for _ in range(5):
        trace_id = str(uuid.uuid4())
        await client.post("/api/v1/outcomes", json={
            "trace_id": trace_id,
            "outcome": "success",
            "retrieved_lesson_ids": [lesson1_id],
        })

    # Report failure for lesson2 several times to reduce its utility
    for _ in range(5):
        trace_id = str(uuid.uuid4())
        await client.post("/api/v1/outcomes", json={
            "trace_id": trace_id,
            "outcome": "failure",
            "retrieved_lesson_ids": [lesson2_id],
        })

    # Retrieve with utility_weight=1.0 — lesson1 should rank first
    # Use keyword mode since embeddings aren't generated (no Celery worker in tests)
    retrieve_resp = await client.post("/api/v1/retrieve", json={
        "query": "database connection timeout retry backoff",
        "agent_id": "rank-test",
        "utility_weight": 1.0,
        "top_k": 5,
        "search_mode": "keyword",
    })
    assert retrieve_resp.status_code == 200
    returned = retrieve_resp.json()["lessons"]
    assert len(returned) >= 2
    ids = [l["id"] for l in returned]
    assert ids.index(lesson1_id) < ids.index(lesson2_id)
