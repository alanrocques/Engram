"""Adapter for integrating TestZeus Hercules test traces with Engram memory service."""

import json
from pathlib import Path
from typing import Any

import httpx

from integrations.shared.outcomes_client import OutcomeReport, OutcomesClient
from integrations.shared.trace_builder import TraceBuilder


AGENT_ID = "hercules-test-v1"
DOMAIN = "test-automation"


class HerculesEngramAdapter:
    """
    Bridge between TestZeus Hercules test execution traces and the Engram
    experiential memory service.

    Handles trace ingestion, lesson retrieval, and outcome reporting.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        agent_id: str = AGENT_ID,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.agent_id = agent_id
        self._builder = TraceBuilder(agent_id=agent_id, domain=DOMAIN)
        self._outcomes = OutcomesClient(base_url=base_url)
        self._client = httpx.Client(
            base_url=f"{self.base_url}/api/v1",
            timeout=30.0,
            headers={"Content-Type": "application/json"},
        )

    def ingest_trace(
        self,
        fixture_path: str | Path,
        *,
        run_id: str | None = None,
    ) -> str:
        """
        Ingest a Hercules test trace fixture into Engram.

        Args:
            fixture_path: Path to a fixture JSON file.
            run_id: Optional run ID to stamp into the trace for dedup avoidance.

        Returns:
            The trace ID assigned by Engram.
        """
        payload = self._builder.build_from_fixture(fixture_path, run_id=run_id)
        response = self._client.post("/traces", json=payload)
        response.raise_for_status()
        data = response.json()
        return data["id"]

    def retrieve_lessons(
        self,
        context: str,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Retrieve relevant lessons from Engram for a given test context.

        Args:
            context: Description of the test scenario or error being encountered.
            top_k: Maximum number of lessons to return.

        Returns:
            List of lesson dicts ranked by relevance.
        """
        payload = {
            "query": context,
            "agent_id": self.agent_id,
            "domain": DOMAIN,
            "top_k": top_k,
            "min_confidence": 0.1,
            "include_context": True,
        }
        response = self._client.post("/retrieve", json=payload)
        response.raise_for_status()
        return response.json()

    def report_outcome(
        self,
        trace_id: str,
        outcome: str,
        retrieved_lesson_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Report the outcome of a test execution to trigger Bellman updates
        and penalty propagation.

        Args:
            trace_id: The Engram trace ID returned from ingest_trace().
            outcome: "success", "failure", or "partial".
            retrieved_lesson_ids: IDs of lessons that were retrieved before this run.

        Returns:
            Outcome response with updated lesson info.
        """
        report = OutcomeReport(
            trace_id=trace_id,
            outcome=outcome,
            retrieved_lesson_ids=retrieved_lesson_ids or [],
            downstream_utility=1.0 if outcome == "success" else 0.0,
            context_similarity=1.0,
        )
        result = self._outcomes.report(report)
        return result.model_dump()

    def list_fixtures(self, outcome: str | None = None) -> list[Path]:
        """
        List available fixture files, optionally filtered by outcome prefix.

        Args:
            outcome: Filter by "success", "failure", or "partial" prefix.

        Returns:
            Sorted list of fixture file paths.
        """
        fixtures_dir = Path(__file__).parent / "fixtures"
        pattern = f"{outcome}_*.json" if outcome else "*.json"
        return sorted(fixtures_dir.glob(pattern))

    def close(self) -> None:
        """Close underlying HTTP clients."""
        self._client.close()
        self._outcomes.close()

    def __enter__(self) -> "HerculesEngramAdapter":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
