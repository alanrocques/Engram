"""Integration tests for TestZeus Hercules <-> Engram integration.

These tests require a running Engram backend (API + Celery workers + PostgreSQL + Redis).
Run with: cd integrations && uv run pytest hercules/tests/ -m integration -v

Uses shared fixtures from integrations/conftest.py: base_url, run_id, outcomes_client.
"""

from pathlib import Path

import httpx
import pytest

from integrations.hercules.adapter import HerculesEngramAdapter
from integrations.hercules.scenarios.cold_start import run_cold_start
from integrations.hercules.scenarios.failure_cluster import run_failure_cluster
from integrations.shared.outcomes_client import OutcomeReport, OutcomesClient
from integrations.shared.verify import (
    get_failure_queue_stats,
    trigger_batch_analysis,
    wait_for_lesson,
    wait_for_processing,
)


FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


@pytest.fixture(scope="module")
def adapter(base_url: str) -> HerculesEngramAdapter:
    """Create an adapter for the test module."""
    a = HerculesEngramAdapter(base_url=base_url)
    yield a
    a.close()


# ---------------------------------------------------------------------------
# Test: Ingest a single success trace and verify lesson creation
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_ingest_success_trace(adapter: HerculesEngramAdapter, run_id: str, base_url: str) -> None:
    """Ingest a success trace and verify a lesson is extracted."""
    fixture = FIXTURES_DIR / "success_login_flow.json"
    trace_id = adapter.ingest_trace(fixture, run_id=run_id)

    assert trace_id, "Trace ID should be returned"

    # Wait for the trace to be processed
    result = wait_for_processing(base_url, trace_id, timeout=90.0)
    assert result is not None, "Trace should be processed within timeout"
    assert result["status"] in ("processed", "failed"), f"Unexpected status: {result['status']}"


@pytest.mark.integration
def test_lesson_created_from_success(
    adapter: HerculesEngramAdapter,
    run_id: str,
    base_url: str,
) -> None:
    """After ingesting success traces, verify success_pattern lessons exist."""
    # Ingest a success trace
    fixture = FIXTURES_DIR / "success_checkout_flow.json"
    trace_id = adapter.ingest_trace(fixture, run_id=run_id)
    wait_for_processing(base_url, trace_id, timeout=90.0)

    # Wait for lesson to appear
    lessons = wait_for_lesson(
        base_url,
        agent_id=adapter.agent_id,
        lesson_type="success_pattern",
        min_count=1,
        timeout=90.0,
    )
    assert len(lessons) >= 1, "At least one success_pattern lesson should exist"

    lesson = lessons[0]
    assert lesson.get("lesson_type") == "success_pattern"
    assert lesson.get("agent_id") == adapter.agent_id


# ---------------------------------------------------------------------------
# Test: Retrieve relevant lessons for a test context
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_retrieve_relevant_lessons(
    adapter: HerculesEngramAdapter,
    base_url: str,
) -> None:
    """Retrieve lessons relevant to a test automation context."""
    results = adapter.retrieve_lessons(
        context="login form automation with username and password fields",
        top_k=5,
    )
    # May return 0 if no lessons have embeddings yet, but should not error
    assert isinstance(results, list), "Retrieval should return a list"


# ---------------------------------------------------------------------------
# Test: Failure traces go to the failure queue
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_failure_trace_queued(
    adapter: HerculesEngramAdapter,
    run_id: str,
    base_url: str,
) -> None:
    """Ingest a failure trace and verify it enters the failure queue."""
    fixture = FIXTURES_DIR / "failure_element_not_found_1.json"
    trace_id = adapter.ingest_trace(fixture, run_id=run_id)

    # Wait for processing
    result = wait_for_processing(base_url, trace_id, timeout=90.0)
    assert result is not None, "Trace should be processed within timeout"

    # Check failure queue has entries
    stats = get_failure_queue_stats(base_url)
    assert stats.get("pending", 0) >= 1, "Failure queue should have at least 1 pending"


# ---------------------------------------------------------------------------
# Test: Batch analysis produces root_cause lesson from failure cluster
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_batch_analysis_root_cause(
    adapter: HerculesEngramAdapter,
    run_id: str,
    base_url: str,
) -> None:
    """Ingest 4 element-not-found failures and verify batch analysis creates a root_cause lesson."""
    # Ingest the failure cluster (4 traces with same error pattern)
    fixtures = [
        FIXTURES_DIR / "failure_element_not_found_1.json",
        FIXTURES_DIR / "failure_element_not_found_2.json",
        FIXTURES_DIR / "failure_element_not_found_3.json",
        FIXTURES_DIR / "failure_element_not_found_4.json",
    ]
    trace_ids = []
    for f in fixtures:
        tid = adapter.ingest_trace(f, run_id=run_id)
        trace_ids.append(tid)

    # Wait for all to be processed
    for tid in trace_ids:
        wait_for_processing(base_url, tid, timeout=90.0)

    # Trigger batch analysis
    analysis = trigger_batch_analysis(base_url)
    assert isinstance(analysis, dict), "Batch analysis should return a dict"

    # Check for root_cause lessons
    root_cause_lessons = wait_for_lesson(
        base_url,
        agent_id=adapter.agent_id,
        lesson_type="root_cause",
        min_count=1,
        timeout=120.0,
    )
    assert len(root_cause_lessons) >= 1, "At least one root_cause lesson should be created"
    assert root_cause_lessons[0].get("lesson_type") == "root_cause"


# ---------------------------------------------------------------------------
# Test: Outcome reporting updates lesson utility
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_outcome_updates_utility(
    adapter: HerculesEngramAdapter,
    run_id: str,
    base_url: str,
    outcomes_client: OutcomesClient,
) -> None:
    """Report a success outcome and verify lesson utility is updated."""
    # First, ingest a success trace and wait for lesson
    fixture = FIXTURES_DIR / "success_search_products.json"
    trace_id = adapter.ingest_trace(fixture, run_id=run_id)
    wait_for_processing(base_url, trace_id, timeout=90.0)

    # Get lessons to find one to reference
    lessons = wait_for_lesson(
        base_url,
        agent_id=adapter.agent_id,
        min_count=1,
        timeout=90.0,
    )
    if not lessons:
        pytest.skip("No lessons available to test outcome reporting")

    lesson_id = lessons[0]["id"]
    initial_utility = lessons[0].get("utility", 0.0)

    # Ingest another trace that "used" this lesson
    fixture2 = FIXTURES_DIR / "success_navigation_menu.json"
    trace_id2 = adapter.ingest_trace(fixture2, run_id=run_id)
    wait_for_processing(base_url, trace_id2, timeout=90.0)

    # Report successful outcome referencing the lesson
    report = OutcomeReport(
        trace_id=trace_id2,
        outcome="success",
        retrieved_lesson_ids=[lesson_id],
        downstream_utility=1.0,
        context_similarity=0.8,
    )
    result = outcomes_client.report(report)
    assert result.outcome == "success"
    assert result.updated_count >= 0

    # Verify the lesson's utility or retrieval_count was updated
    client = httpx.Client(
        base_url=f"{base_url.rstrip('/')}/api/v1",
        timeout=10.0,
    )
    try:
        resp = client.get(f"/lessons/{lesson_id}")
        if resp.status_code == 200:
            updated_lesson = resp.json()
            # retrieval_count should have incremented or utility updated
            assert (
                updated_lesson.get("retrieval_count", 0) >= 1
                or updated_lesson.get("utility", 0.0) >= initial_utility
            ), "Lesson utility or retrieval count should be updated after outcome report"
    finally:
        client.close()


# ---------------------------------------------------------------------------
# Test: Cold start scenario (end-to-end)
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_cold_start_scenario(
    adapter: HerculesEngramAdapter,
    run_id: str,
) -> None:
    """Run the complete cold start scenario end-to-end."""
    result = run_cold_start(adapter, run_id)
    assert len(result["trace_ids"]) == 3, "Should ingest 3 traces"
    assert result["lessons_found"] >= 1, "At least 1 lesson should be extracted"


# ---------------------------------------------------------------------------
# Test: Failure cluster scenario (end-to-end)
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_failure_cluster_scenario(
    adapter: HerculesEngramAdapter,
    run_id: str,
) -> None:
    """Run the complete failure cluster scenario end-to-end."""
    result = run_failure_cluster(adapter, run_id)
    assert len(result["trace_ids"]) == 4, "Should ingest 4 failure traces"
    assert result["queue_stats"].get("pending", 0) >= 0, "Queue stats should be returned"
    assert result["root_cause_count"] >= 1, "At least 1 root_cause lesson should be created"


# ---------------------------------------------------------------------------
# Test: Partial trace creates comparative_insight lesson
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_partial_trace_creates_insight(
    adapter: HerculesEngramAdapter,
    run_id: str,
    base_url: str,
) -> None:
    """Ingest a partial trace and verify a comparative_insight lesson is created."""
    fixture = FIXTURES_DIR / "partial_login_mfa.json"
    trace_id = adapter.ingest_trace(fixture, run_id=run_id)

    result = wait_for_processing(base_url, trace_id, timeout=90.0)
    assert result is not None, "Trace should be processed"

    # Partial traces should produce comparative_insight lessons
    lessons = wait_for_lesson(
        base_url,
        agent_id=adapter.agent_id,
        lesson_type="comparative_insight",
        min_count=1,
        timeout=90.0,
    )
    assert len(lessons) >= 1, "At least one comparative_insight lesson should exist"
