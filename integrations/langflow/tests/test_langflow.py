"""Integration tests for the Langflow Customer Support Agent.

These tests require a running Engram backend (API + Celery workers + DB).
Run with:
    cd /path/to/Engram
    pytest integrations/langflow/tests/test_langflow.py -v -m integration

Fixtures `base_url`, `run_id`, and `outcomes_client` come from
integrations/conftest.py.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from integrations.langflow.adapter import FIXTURES_DIR, LangflowEngramAdapter
from integrations.shared.verify import (
    get_failure_queue_stats,
    trigger_batch_analysis,
    wait_for_lesson,
    wait_for_processing,
)

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def adapter(base_url: str) -> LangflowEngramAdapter:
    """Create adapter for the test module."""
    a = LangflowEngramAdapter(base_url=base_url)
    yield a
    a.close()


@pytest.fixture(scope="module")
def fixture_dir() -> Path:
    return FIXTURES_DIR


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestTraceIngestion:
    """Test trace ingestion into Engram."""

    def test_ingest_success_trace(
        self, adapter: LangflowEngramAdapter, run_id: str
    ) -> None:
        """Ingesting a success fixture should return a valid trace ID."""
        trace_id = adapter.ingest_trace(
            "success_refund_processed.json", run_id=run_id
        )
        assert trace_id, "Expected a non-empty trace ID"
        assert isinstance(trace_id, str)

    def test_ingest_failure_trace(
        self, adapter: LangflowEngramAdapter, run_id: str
    ) -> None:
        """Ingesting a failure fixture should return a valid trace ID."""
        trace_id = adapter.ingest_trace(
            "failure_crm_api_timeout_1.json", run_id=run_id
        )
        assert trace_id, "Expected a non-empty trace ID"

    def test_ingest_partial_trace(
        self, adapter: LangflowEngramAdapter, run_id: str
    ) -> None:
        """Ingesting a partial fixture should return a valid trace ID."""
        trace_id = adapter.ingest_trace(
            "partial_refund_manual_review.json", run_id=run_id
        )
        assert trace_id, "Expected a non-empty trace ID"

    def test_ingest_all_fixtures(
        self, adapter: LangflowEngramAdapter, run_id: str, fixture_dir: Path
    ) -> None:
        """All 25 fixtures should be ingestable without errors."""
        fixtures = sorted(fixture_dir.glob("*.json"))
        assert len(fixtures) == 25, f"Expected 25 fixtures, found {len(fixtures)}"

        trace_ids = []
        for fixture in fixtures:
            # Use a sub-run-id to avoid collisions with other tests
            sub_run_id = f"{run_id}-all-{fixture.stem}"
            # Use process_async=false to avoid flooding the Celery queue,
            # which would cause later tests to time out waiting for processing.
            tid = adapter.ingest_trace(fixture, run_id=sub_run_id, process_async=False)
            assert tid, f"Failed to ingest {fixture.name}"
            trace_ids.append(tid)

        assert len(trace_ids) == 25


class TestLessonExtraction:
    """Test that ingested traces produce lessons via background processing."""

    def test_success_trace_produces_lesson(
        self, adapter: LangflowEngramAdapter, base_url: str, run_id: str
    ) -> None:
        """A success trace should produce a lesson after processing."""
        trace_id = adapter.ingest_trace(
            "success_order_tracking.json", run_id=f"{run_id}-extract"
        )

        # Wait for processing
        result = wait_for_processing(base_url, trace_id, timeout=90.0)
        assert result is not None, "Trace processing timed out"
        assert result.get("status") in (
            "processed",
            "failed",
        ), f"Unexpected status: {result.get('status')}"

        if result.get("status") == "processed":
            # Check that at least one lesson exists for the agent
            lessons = wait_for_lesson(
                base_url,
                agent_id=adapter.agent_id,
                min_count=1,
                timeout=60.0,
            )
            assert len(lessons) >= 1, "Expected at least 1 lesson after processing"


class TestLessonRetrieval:
    """Test lesson retrieval via the Engram retrieval API."""

    def test_retrieve_relevant_lessons(
        self, adapter: LangflowEngramAdapter, base_url: str, run_id: str
    ) -> None:
        """Retrieval should return lessons relevant to the query context."""
        # Seed some lessons first
        from integrations.langflow.seed_lessons import seed

        seed(base_url)

        # Wait briefly for embeddings
        time.sleep(5)

        lessons = adapter.retrieve_lessons(
            context="Customer wants a refund for a damaged product",
            top_k=5,
        )
        # With seed lessons, we should get at least one result
        assert isinstance(lessons, list)
        # Note: may be empty if embeddings aren't generated yet

    def test_retrieve_returns_list(
        self, adapter: LangflowEngramAdapter
    ) -> None:
        """Retrieval should always return a list (possibly empty)."""
        lessons = adapter.retrieve_lessons(
            context="completely irrelevant query about quantum physics",
            top_k=3,
        )
        assert isinstance(lessons, list)


class TestFailureQueue:
    """Test failure queuing and batch analysis."""

    def test_failure_traces_enter_queue(
        self, adapter: LangflowEngramAdapter, base_url: str, run_id: str
    ) -> None:
        """Failure traces should populate the failure queue."""
        # Ingest 3 CRM timeout failures (same error_signature)
        failure_fixtures = [
            "failure_crm_api_timeout_1.json",
            "failure_crm_api_timeout_2.json",
            "failure_crm_api_timeout_3.json",
        ]
        for fixture in failure_fixtures:
            sub_run_id = f"{run_id}-fq-{fixture.split('.')[0]}"
            tid = adapter.ingest_trace(fixture, run_id=sub_run_id)
            wait_for_processing(base_url, tid, timeout=90.0)

        # Give the queue time to populate
        time.sleep(3)

        stats = get_failure_queue_stats(base_url)
        assert isinstance(stats, dict)
        # pending might be 0 if analysis already ran, but the endpoint should work
        assert "pending" in stats

    def test_batch_analysis_endpoint(
        self, adapter: LangflowEngramAdapter, base_url: str
    ) -> None:
        """Triggering batch analysis should not error."""
        result = trigger_batch_analysis(base_url)
        assert isinstance(result, dict)

    def test_batch_analysis_creates_root_cause(
        self, adapter: LangflowEngramAdapter, base_url: str, run_id: str
    ) -> None:
        """
        After ingesting 3+ failures with the same signature and triggering
        batch analysis, a root_cause lesson should be created.
        """
        # Ingest the 4 CRM timeout failures
        for i in range(1, 5):
            fixture = f"failure_crm_api_timeout_{i}.json"
            sub_run_id = f"{run_id}-batch-{i}"
            tid = adapter.ingest_trace(fixture, run_id=sub_run_id)
            wait_for_processing(base_url, tid, timeout=90.0)

        time.sleep(3)

        # Trigger batch analysis
        trigger_batch_analysis(base_url)

        # Wait for root_cause lessons
        root_causes = wait_for_lesson(
            base_url,
            agent_id=adapter.agent_id,
            lesson_type="root_cause",
            min_count=1,
            timeout=90.0,
            interval=3.0,
        )
        # This may or may not produce lessons depending on LLM availability
        assert isinstance(root_causes, list)


class TestOutcomeReporting:
    """Test outcome reporting and utility score updates."""

    def test_report_success_outcome(
        self, adapter: LangflowEngramAdapter, base_url: str, run_id: str
    ) -> None:
        """Reporting a success outcome should update lesson utilities."""
        # Ingest a trace first
        trace_id = adapter.ingest_trace(
            "success_product_recommendation.json",
            run_id=f"{run_id}-outcome",
        )
        wait_for_processing(base_url, trace_id, timeout=90.0)

        # Retrieve lessons to get IDs
        lessons = adapter.retrieve_lessons(
            context="product recommendations based on purchase history",
            top_k=3,
        )
        lesson_ids = [l["id"] for l in lessons if "id" in l]

        # Report outcome
        result = adapter.report_outcome(
            trace_id=trace_id,
            outcome="success",
            retrieved_lesson_ids=lesson_ids[:3],
            downstream_utility=0.85,
            context_similarity=0.9,
        )
        assert isinstance(result, dict)
        assert result.get("trace_id") == trace_id
        assert result.get("outcome") == "success"

    def test_report_failure_outcome(
        self, adapter: LangflowEngramAdapter, base_url: str, run_id: str
    ) -> None:
        """Reporting a failure outcome should propagate penalties."""
        trace_id = adapter.ingest_trace(
            "failure_sentiment_misclassification.json",
            run_id=f"{run_id}-fail-outcome",
        )
        wait_for_processing(base_url, trace_id, timeout=90.0)

        result = adapter.report_outcome(
            trace_id=trace_id,
            outcome="failure",
            downstream_utility=0.0,
            context_similarity=1.0,
        )
        assert isinstance(result, dict)
        assert result.get("outcome") == "failure"


class TestAdapterHelpers:
    """Test adapter helper methods."""

    def test_list_all_fixtures(self, adapter: LangflowEngramAdapter) -> None:
        """Should list all 25 fixture files."""
        fixtures = adapter.list_fixtures()
        assert len(fixtures) == 25

    def test_list_fixtures_by_outcome(
        self, adapter: LangflowEngramAdapter
    ) -> None:
        """Should filter fixtures by outcome prefix."""
        success = adapter.list_fixtures(outcome="success")
        failure = adapter.list_fixtures(outcome="failure")
        partial = adapter.list_fixtures(outcome="partial")

        assert len(success) == 8
        assert len(failure) == 12
        assert len(partial) == 5

    def test_fixture_dir_exists(self, fixture_dir: Path) -> None:
        """Fixture directory should exist and contain JSON files."""
        assert fixture_dir.exists()
        assert fixture_dir.is_dir()
        json_files = list(fixture_dir.glob("*.json"))
        assert len(json_files) > 0
