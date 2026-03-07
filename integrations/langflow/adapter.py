"""Langflow Customer Support Agent adapter for Engram.

Wraps the shared TraceBuilder and OutcomesClient to provide a clean
interface for ingesting traces, retrieving lessons, and reporting
outcomes specific to the langflow-support-v1 agent.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx

from integrations.shared.outcomes_client import OutcomeReport, OutcomesClient
from integrations.shared.trace_builder import TraceBuilder

AGENT_ID = "langflow-support-v1"
DOMAIN = "customer-support"
FIXTURES_DIR = Path(__file__).parent / "fixtures"


class LangflowEngramAdapter:
    """Adapter connecting the Langflow support agent to Engram's memory layer."""

    def __init__(
        self,
        base_url: str = "",
        agent_id: str = AGENT_ID,
    ) -> None:
        self.base_url = (
            base_url.rstrip("/")
            or os.environ.get("ENGRAM_BASE_URL", "http://localhost:8000")
        )
        self.agent_id = agent_id
        self.domain = DOMAIN

        self._trace_builder = TraceBuilder(agent_id=agent_id, domain=DOMAIN)
        self._outcomes_client = OutcomesClient(base_url=self.base_url)
        self._http = httpx.Client(
            base_url=f"{self.base_url}/api/v1",
            timeout=30.0,
            headers={"Content-Type": "application/json"},
        )

    # -- Trace Ingestion --

    def ingest_trace(
        self,
        fixture_path: str | Path,
        *,
        run_id: str | None = None,
    ) -> str:
        """
        Ingest a trace from a fixture JSON file.

        Args:
            fixture_path: Path to the fixture JSON file (absolute or relative to fixtures/).
            run_id: Unique run ID to stamp into the trace for dedup avoidance.

        Returns:
            The trace ID assigned by the Engram API.
        """
        path = self._resolve_fixture_path(fixture_path)
        payload = self._trace_builder.build_from_fixture(path, run_id=run_id)
        resp = self._http.post("/traces", json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["id"]

    def ingest_trace_raw(
        self,
        trace_data: dict[str, Any],
        outcome: str = "unknown",
        *,
        run_id: str | None = None,
    ) -> str:
        """
        Ingest a trace from raw data (not a fixture file).

        Returns:
            The trace ID assigned by the Engram API.
        """
        payload = self._trace_builder.build_trace(
            content=trace_data,
            outcome=outcome,
            run_id=run_id,
        )
        resp = self._http.post("/traces", json=payload)
        resp.raise_for_status()
        return resp.json()["id"]

    # -- Lesson Retrieval --

    def retrieve_lessons(
        self,
        context: str,
        top_k: int = 5,
        min_confidence: float = 0.1,
    ) -> list[dict[str, Any]]:
        """
        Retrieve relevant lessons from Engram's memory pool.

        Args:
            context: Description of the current task or situation.
            top_k: Maximum number of lessons to return.
            min_confidence: Minimum confidence threshold for returned lessons.

        Returns:
            List of lesson dicts, ranked by relevance.
        """
        payload = {
            "query": context,
            "agent_id": self.agent_id,
            "domain": self.domain,
            "top_k": top_k,
            "min_confidence": min_confidence,
            "include_context": True,
        }
        resp = self._http.post("/retrieve", json=payload)
        resp.raise_for_status()
        data = resp.json()
        # The retrieve endpoint returns {"lessons": [...]} or a list directly
        if isinstance(data, dict) and "lessons" in data:
            return data["lessons"]
        if isinstance(data, list):
            return data
        return []

    # -- Outcome Reporting --

    def report_outcome(
        self,
        trace_id: str,
        outcome: str,
        retrieved_lesson_ids: list[str] | None = None,
        downstream_utility: float = 0.0,
        context_similarity: float = 1.0,
    ) -> dict[str, Any]:
        """
        Report the outcome of a trace execution.

        Triggers Bellman utility updates and failure penalty propagation
        in the Engram backend.

        Args:
            trace_id: ID of the trace being reported on.
            outcome: success/failure/partial.
            retrieved_lesson_ids: IDs of lessons retrieved for this trace.
            downstream_utility: How useful the retrieved lessons were (0.0-1.0).
            context_similarity: How similar the current context was to lesson contexts.

        Returns:
            Outcome response with updated lesson info.
        """
        report = OutcomeReport(
            trace_id=trace_id,
            outcome=outcome,
            retrieved_lesson_ids=retrieved_lesson_ids or [],
            downstream_utility=downstream_utility,
            context_similarity=context_similarity,
        )
        result = self._outcomes_client.report(report)
        return result.model_dump()

    # -- Helpers --

    def list_fixtures(self, outcome: str | None = None) -> list[Path]:
        """List available fixture files, optionally filtered by outcome prefix."""
        pattern = f"{outcome}_*.json" if outcome else "*.json"
        return sorted(FIXTURES_DIR.glob(pattern))

    def get_lessons(
        self,
        limit: int = 100,
        lesson_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch lessons from the API, optionally filtered by type."""
        params: dict[str, Any] = {"limit": limit}
        if lesson_type:
            params["type"] = lesson_type
        resp = self._http.get("/lessons", params=params)
        resp.raise_for_status()
        return resp.json()

    def get_failure_queue_stats(self) -> dict[str, Any]:
        """Fetch failure queue statistics."""
        resp = self._http.get("/failure-queue/stats")
        resp.raise_for_status()
        return resp.json()

    def trigger_batch_analysis(self) -> dict[str, Any]:
        """Trigger batch failure analysis."""
        resp = self._http.post("/failure-queue/analyze")
        resp.raise_for_status()
        return resp.json()

    def close(self) -> None:
        """Close HTTP clients."""
        self._http.close()
        self._outcomes_client.close()

    def __enter__(self) -> LangflowEngramAdapter:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def _resolve_fixture_path(self, path: str | Path) -> Path:
        """Resolve fixture path — use absolute if given, else relative to fixtures dir."""
        p = Path(path)
        if p.is_absolute():
            return p
        # Try relative to fixtures directory
        fixture_path = FIXTURES_DIR / p
        if fixture_path.exists():
            return fixture_path
        # Try adding .json extension
        fixture_path_json = FIXTURES_DIR / f"{p}.json"
        if fixture_path_json.exists():
            return fixture_path_json
        # Fall back to the original path (will error on load if not found)
        return p
