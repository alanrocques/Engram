"""Shared pytest fixtures for Engram integration tests."""

import os

import pytest

from integrations.shared.outcomes_client import OutcomesClient
from integrations.shared.trace_builder import generate_run_id


ENGRAM_BASE_URL = os.environ.get("ENGRAM_BASE_URL", "http://localhost:8000")


@pytest.fixture(scope="session")
def base_url() -> str:
    """Base URL for the Engram API."""
    return ENGRAM_BASE_URL


@pytest.fixture(scope="session")
def run_id() -> str:
    """Unique run ID for this test session to avoid dedup collisions."""
    return generate_run_id()


@pytest.fixture(scope="session")
def outcomes_client(base_url: str) -> OutcomesClient:
    """Outcomes client for reporting trace results."""
    client = OutcomesClient(base_url=base_url)
    yield client
    client.close()
