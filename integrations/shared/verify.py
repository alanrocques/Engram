"""Polling and verification helpers for integration tests."""

import time
from typing import Any, Callable

import httpx


def poll_until(
    check_fn: Callable[[], bool],
    timeout: float = 30.0,
    interval: float = 1.0,
    description: str = "condition",
) -> bool:
    """
    Poll check_fn until it returns True or timeout is reached.

    Returns True if the condition was met, False on timeout.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        if check_fn():
            return True
        time.sleep(interval)
    return False


def wait_for_processing(
    base_url: str,
    trace_id: str,
    timeout: float = 60.0,
    interval: float = 2.0,
) -> dict[str, Any] | None:
    """
    Poll GET /api/v1/traces/{trace_id} until status is 'processed' or 'failed'.

    Returns the trace response dict, or None on timeout.
    """
    client = httpx.Client(base_url=f"{base_url.rstrip('/')}/api/v1", timeout=10.0)
    try:
        deadline = time.time() + timeout
        while time.time() < deadline:
            resp = client.get(f"/traces/{trace_id}")
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") in ("processed", "failed"):
                    return data
            time.sleep(interval)
        return None
    finally:
        client.close()


def wait_for_lesson(
    base_url: str,
    *,
    agent_id: str | None = None,
    lesson_type: str | None = None,
    min_count: int = 1,
    timeout: float = 60.0,
    interval: float = 2.0,
) -> list[dict[str, Any]]:
    """
    Poll GET /api/v1/lessons until at least min_count lessons match the filters.

    Returns the list of matching lessons, or empty list on timeout.
    """
    client = httpx.Client(base_url=f"{base_url.rstrip('/')}/api/v1", timeout=10.0)
    try:
        deadline = time.time() + timeout
        while time.time() < deadline:
            params: dict[str, Any] = {"limit": 100}
            if lesson_type:
                params["type"] = lesson_type
            resp = client.get("/lessons", params=params)
            if resp.status_code == 200:
                lessons = resp.json()
                if isinstance(lessons, list):
                    filtered = lessons
                    if agent_id:
                        filtered = [l for l in filtered if l.get("agent_id") == agent_id]
                    if len(filtered) >= min_count:
                        return filtered
            time.sleep(interval)
        return []
    finally:
        client.close()


def get_failure_queue_stats(base_url: str) -> dict[str, Any]:
    """Fetch failure queue stats."""
    client = httpx.Client(base_url=f"{base_url.rstrip('/')}/api/v1", timeout=10.0)
    try:
        resp = client.get("/failure-queue/stats")
        resp.raise_for_status()
        return resp.json()
    finally:
        client.close()


def trigger_batch_analysis(base_url: str) -> dict[str, Any]:
    """Trigger batch failure analysis."""
    client = httpx.Client(base_url=f"{base_url.rstrip('/')}/api/v1", timeout=30.0)
    try:
        resp = client.post("/failure-queue/analyze")
        resp.raise_for_status()
        return resp.json()
    finally:
        client.close()
