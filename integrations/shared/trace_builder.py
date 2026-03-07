"""Utilities for building and loading trace fixtures for Engram integration tests."""

import hashlib
import json
import uuid
from pathlib import Path
from typing import Any


class TraceBuilder:
    """Build trace payloads compatible with the Engram TraceCreate schema."""

    def __init__(self, agent_id: str, domain: str = "general"):
        self.agent_id = agent_id
        self.domain = domain

    def build_trace(
        self,
        *,
        content: dict[str, Any],
        outcome: str = "unknown",
        run_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Build a trace payload for POST /api/v1/traces.

        Args:
            content: The trace data (spans, actions, etc.)
            outcome: success/failure/partial/unknown — routes extraction
            run_id: Unique run ID to prevent dedup collisions across test runs
        """
        if run_id:
            content = add_run_id(content, run_id)

        return {
            "agent_id": self.agent_id,
            "trace_data": content,
            "span_count": len(content.get("spans", [])),
            "outcome": outcome,
        }

    def build_from_fixture(
        self,
        fixture_path: str | Path,
        *,
        outcome: str | None = None,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Load a fixture JSON file and build a trace payload.

        The fixture file should contain a dict with at least "trace_data".
        Optionally includes "outcome" which can be overridden.
        """
        data = load_fixture(fixture_path)
        trace_data = data.get("trace_data", data)
        trace_outcome = outcome or data.get("outcome", "unknown")
        return self.build_trace(content=trace_data, outcome=trace_outcome, run_id=run_id)


def add_run_id(content: dict[str, Any], run_id: str) -> dict[str, Any]:
    """
    Stamp a unique run_id into the trace content to avoid SHA-256 dedup
    collisions across test runs.
    """
    stamped = dict(content)
    stamped["_run_id"] = run_id
    return stamped


def load_fixture(path: str | Path) -> dict[str, Any]:
    """Load a JSON fixture file and return its content."""
    with open(path) as f:
        return json.load(f)


def generate_run_id() -> str:
    """Generate a unique run ID for a test session."""
    return uuid.uuid4().hex[:12]


def content_hash(content: dict[str, Any]) -> str:
    """Compute the SHA-256 hash of trace content (matches backend dedup logic)."""
    serialized = json.dumps(content, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode()).hexdigest()
