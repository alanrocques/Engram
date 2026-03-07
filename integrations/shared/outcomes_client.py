"""Client wrapper for POST /api/v1/outcomes — reports trace outcomes to Engram."""

import httpx
from pydantic import BaseModel


class OutcomeReport(BaseModel):
    """Maps to OutcomeRequest schema."""

    trace_id: str
    outcome: str  # success/failure/partial
    retrieved_lesson_ids: list[str] = []
    downstream_utility: float = 0.0
    context_similarity: float = 1.0


class OutcomeResult(BaseModel):
    """Maps to OutcomeResponse schema."""

    trace_id: str
    outcome: str
    updated_lesson_ids: list[str]
    updated_count: int


class OutcomesClient:
    """
    Wraps POST /api/v1/outcomes for reporting trace outcomes.

    The SDK's report_outcome() calls POST /traces/{id}/process which only
    reprocesses the trace — it doesn't trigger the Bellman update + penalty
    propagation pipeline. This client calls the proper outcomes endpoint.
    """

    def __init__(self, base_url: str = "http://localhost:8000", timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            base_url=f"{self.base_url}/api/v1",
            timeout=timeout,
            headers={"Content-Type": "application/json"},
        )

    def report(self, report: OutcomeReport) -> OutcomeResult:
        """Report an outcome and trigger utility updates + penalty propagation."""
        response = self._client.post(
            "/outcomes",
            json={
                "trace_id": report.trace_id,
                "outcome": report.outcome,
                "retrieved_lesson_ids": report.retrieved_lesson_ids,
                "downstream_utility": report.downstream_utility,
                "context_similarity": report.context_similarity,
            },
        )
        response.raise_for_status()
        return OutcomeResult(**response.json())

    def close(self) -> None:
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
