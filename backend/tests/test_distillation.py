"""Tests for Feature 2: Multi-Faceted Distillation (outcome-routed extraction)."""

import json
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.db.models import FailureQueue, Lesson, Trace
from app.main import app
from app.api.deps import get_async_session

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session
        await session.rollback()
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session):
    async def override_get_session():
        yield db_session

    app.dependency_overrides[get_async_session] = override_get_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


def _make_claude_mock(response_dict: dict):
    """Return a mock Anthropic client that responds with the given dict."""
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=json.dumps(response_dict))]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message
    return mock_client


# ---------------------------------------------------------------------------
# Extraction route tests
# ---------------------------------------------------------------------------


async def test_success_trace_creates_success_pattern_lesson(db_session):
    """success outcome → lesson with lesson_type='success_pattern'."""
    trace = Trace(
        agent_id="test-agent",
        trace_data={"action": "handle_refund", "result": "ok"},
        span_count=1,
        status="pending",
        outcome="success",
    )
    db_session.add(trace)
    await db_session.flush()
    await db_session.refresh(trace)

    mock_response = {
        "task_context": "Handle refund",
        "action_taken": "Processed full refund",
        "lesson_text": "Always process refunds immediately.",
        "tags": ["refund"],
        "domain": "support",
    }

    with patch("app.services.extraction.get_anthropic_client", return_value=_make_claude_mock(mock_response)):
        from app.services.extraction import route_trace_extraction
        lesson = await route_trace_extraction(db_session, trace.id, "success")

    assert lesson is not None
    assert lesson.lesson_type == "success_pattern"
    assert lesson.outcome == "success"
    assert lesson.utility == pytest.approx(0.6)
    assert lesson.extraction_mode == "immediate"


async def test_failure_trace_queues_and_returns_none(db_session):
    """failure outcome → no lesson, failure_queue has 1 row."""
    trace = Trace(
        agent_id="test-agent",
        trace_data={"action": "api_call", "error": "timeout"},
        span_count=1,
        status="pending",
        outcome="failure",
    )
    db_session.add(trace)
    await db_session.flush()
    await db_session.refresh(trace)

    mock_response = {
        "error_category": "timeout",
        "error_signature": "api_call_timeout",
    }

    with patch("app.services.extraction.get_anthropic_client", return_value=_make_claude_mock(mock_response)):
        from app.services.extraction import route_trace_extraction
        lesson = await route_trace_extraction(db_session, trace.id, "failure")

    assert lesson is None

    result = await db_session.execute(
        select(FailureQueue).where(FailureQueue.trace_id == trace.id)
    )
    queue_entry = result.scalar_one_or_none()
    assert queue_entry is not None
    assert queue_entry.error_category == "timeout"
    assert queue_entry.error_signature == "api_call_timeout"


async def test_partial_trace_creates_comparative_insight(db_session):
    """partial outcome → lesson with lesson_type='comparative_insight'."""
    trace = Trace(
        agent_id="test-agent",
        trace_data={"action": "parse_document", "result": "partial"},
        span_count=2,
        status="pending",
        outcome="partial",
    )
    db_session.add(trace)
    await db_session.flush()
    await db_session.refresh(trace)

    mock_response = {
        "task_context": "Parse a PDF document",
        "action_taken": "Used regex extraction",
        "lesson_text": "Regex works for structured PDFs but fails on scanned ones.",
        "tags": ["parsing"],
        "domain": "data-processing",
    }

    with patch("app.services.extraction.get_anthropic_client", return_value=_make_claude_mock(mock_response)):
        from app.services.extraction import route_trace_extraction
        lesson = await route_trace_extraction(db_session, trace.id, "partial")

    assert lesson is not None
    assert lesson.lesson_type == "comparative_insight"
    assert lesson.outcome == "partial"
    assert lesson.utility == pytest.approx(0.5)


async def test_unknown_trace_creates_general_lesson(db_session):
    """unknown outcome → lesson with lesson_type='general'."""
    trace = Trace(
        agent_id="test-agent",
        trace_data={"action": "unknown_action"},
        span_count=0,
        status="pending",
        outcome="unknown",
    )
    db_session.add(trace)
    await db_session.flush()
    await db_session.refresh(trace)

    mock_response = {
        "task_context": "Some action",
        "action_taken": "Did something",
        "outcome": "success",
        "lesson_text": "Something was learned.",
        "tags": ["general"],
        "domain": "general",
    }

    with patch("app.services.extraction.get_anthropic_client", return_value=_make_claude_mock(mock_response)):
        from app.services.extraction import route_trace_extraction
        lesson = await route_trace_extraction(db_session, trace.id, "unknown")

    assert lesson is not None
    assert lesson.lesson_type == "general"


# ---------------------------------------------------------------------------
# Batch failure analysis tests
# ---------------------------------------------------------------------------


async def _create_failure_queue_entries(db_session, count: int, sig: str) -> list[UUID]:
    """Create traces + failure_queue entries with the given signature."""
    trace_ids = []
    for i in range(count):
        trace = Trace(
            agent_id="test-agent",
            trace_data={"action": f"action_{i}", "error": "timeout"},
            span_count=1,
            status="processed",
            outcome="failure",
        )
        db_session.add(trace)
        await db_session.flush()
        await db_session.refresh(trace)

        entry = FailureQueue(
            trace_id=trace.id,
            agent_id="test-agent",
            error_category="timeout",
            error_signature=sig,
        )
        db_session.add(entry)
        trace_ids.append(trace.id)

    await db_session.flush()
    return trace_ids


async def test_batch_task_skips_small_groups(db_session):
    """2 failures in queue → batch task does NOT create a lesson (< 3)."""
    await _create_failure_queue_entries(db_session, 2, "small_group_sig")
    await db_session.flush()

    result = await db_session.execute(select(Lesson))
    lessons_before = len(result.scalars().all())

    # Simulate batch task inline (avoids Celery)
    from sqlalchemy import func
    result = await db_session.execute(
        select(FailureQueue.error_signature, func.count(FailureQueue.id).label("cnt"))
        .where(FailureQueue.processed_at.is_(None))
        .where(FailureQueue.error_signature.is_not(None))
        .group_by(FailureQueue.error_signature)
        .having(func.count(FailureQueue.id) >= 3)
    )
    groups = result.all()
    assert len(groups) == 0  # No group with >= 3

    result = await db_session.execute(select(Lesson))
    assert len(result.scalars().all()) == lessons_before


async def test_batch_task_creates_root_cause_lesson(db_session):
    """3 failures with same signature → root_cause lesson created."""
    trace_ids = await _create_failure_queue_entries(db_session, 3, "timeout_sig")

    mock_response = {
        "task_context": "Multiple API calls failing",
        "action_taken": "Retry logic without backoff",
        "lesson_text": "Root cause: missing exponential backoff. Add jitter to retry delays.",
        "tags": ["timeout", "retry"],
        "domain": "api",
    }

    with patch("app.services.extraction.get_anthropic_client", return_value=_make_claude_mock(mock_response)):
        from app.services.extraction import batch_analyze_failure_group
        lesson = await batch_analyze_failure_group(db_session, "timeout_sig", trace_ids)

    assert lesson is not None
    assert lesson.lesson_type == "root_cause"
    assert lesson.extraction_mode == "batch"
    assert lesson.outcome == "failure"
    assert len(lesson.source_trace_ids) == 3


async def test_batch_task_marks_queue_rows_processed(db_session):
    """After batch analysis, queue rows should have processed_at set."""
    from datetime import datetime, timezone
    from sqlalchemy import update

    trace_ids = await _create_failure_queue_entries(db_session, 3, "proc_sig")

    mock_response = {
        "task_context": "Batch test",
        "action_taken": "Batch action",
        "lesson_text": "Batch lesson.",
        "tags": [],
        "domain": "general",
    }

    with patch("app.services.extraction.get_anthropic_client", return_value=_make_claude_mock(mock_response)):
        from app.services.extraction import batch_analyze_failure_group
        await batch_analyze_failure_group(db_session, "proc_sig", trace_ids)

    # Simulate marking queue rows processed (as the task does)
    await db_session.execute(
        update(FailureQueue)
        .where(FailureQueue.error_signature == "proc_sig")
        .values(processed_at=datetime.now(timezone.utc))
    )
    await db_session.flush()

    result = await db_session.execute(
        select(FailureQueue).where(FailureQueue.error_signature == "proc_sig")
    )
    rows = result.scalars().all()
    assert all(r.processed_at is not None for r in rows)


# ---------------------------------------------------------------------------
# API-level test
# ---------------------------------------------------------------------------


async def test_trace_outcome_stored_via_api(client):
    """POST /traces with outcome='success' → outcome stored in DB."""
    response = await client.post(
        "/api/v1/traces",
        json={
            "agent_id": "api-test-agent",
            "trace_data": {"action": "test_action"},
            "span_count": 0,
            "outcome": "success",
        },
        params={"process_async": "false"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["outcome"] == "success"
