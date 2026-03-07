"""Cold Start scenario for the Langflow Customer Support Agent.

Validates that Engram can ingest initial traces, extract lessons,
and serve them back via retrieval — the minimum viable learning loop.

Usage:
    from integrations.langflow.adapter import LangflowEngramAdapter
    from integrations.langflow.scenarios.cold_start import run_cold_start

    adapter = LangflowEngramAdapter()
    result = run_cold_start(adapter, run_id="test-001")
"""

from __future__ import annotations

from typing import Any

from integrations.shared.verify import wait_for_lesson, wait_for_processing


def run_cold_start(
    adapter: Any,
    run_id: str,
    *,
    timeout: float = 90.0,
) -> dict[str, Any]:
    """
    Run the cold start scenario.

    Steps:
        1. Ingest 3 success traces (refund, order tracking, password reset)
        2. Wait for each trace to be processed (lesson extraction)
        3. Verify that lessons were created from the traces
        4. Retrieve lessons using a relevant query
        5. Return a summary of what was created and retrieved

    Args:
        adapter: LangflowEngramAdapter instance.
        run_id: Unique run ID to prevent dedup collisions.
        timeout: Max seconds to wait for processing per trace.

    Returns:
        Dict with trace_ids, lesson_count, retrieved_lessons, and success flag.
    """
    print(f"[cold_start] Starting cold start scenario (run_id={run_id})")

    # Step 1: Ingest 3 success traces
    fixtures = [
        "success_refund_processed.json",
        "success_order_tracking.json",
        "success_password_reset.json",
    ]

    trace_ids: list[str] = []
    for fixture in fixtures:
        trace_id = adapter.ingest_trace(fixture, run_id=run_id)
        trace_ids.append(trace_id)
        print(f"  Ingested {fixture} -> trace_id={trace_id}")

    # Step 2: Wait for processing
    print("[cold_start] Waiting for trace processing...")
    processed_count = 0
    for trace_id in trace_ids:
        result = wait_for_processing(
            adapter.base_url,
            trace_id,
            timeout=timeout,
            interval=2.0,
        )
        if result and result.get("status") == "processed":
            processed_count += 1
            print(f"  Trace {trace_id}: processed")
        else:
            status = result.get("status", "timeout") if result else "timeout"
            print(f"  Trace {trace_id}: {status}")

    # Step 3: Verify lessons were created
    print("[cold_start] Checking for extracted lessons...")
    lessons = wait_for_lesson(
        adapter.base_url,
        agent_id=adapter.agent_id,
        min_count=1,
        timeout=timeout,
        interval=3.0,
    )
    lesson_count = len(lessons)
    print(f"  Found {lesson_count} lessons for agent '{adapter.agent_id}'")

    # Step 4: Retrieve lessons with a relevant query
    print("[cold_start] Retrieving lessons for 'customer refund request'...")
    retrieved = adapter.retrieve_lessons(
        context="Customer is requesting a refund for a recent order",
        top_k=5,
    )
    print(f"  Retrieved {len(retrieved)} lessons")
    for lesson in retrieved[:3]:
        snippet = str(lesson.get("lesson_text", lesson.get("content", "")))[:80]
        print(f"    - {snippet}...")

    # Build result summary
    success = processed_count >= 2 and lesson_count >= 1
    result_summary = {
        "scenario": "cold_start",
        "run_id": run_id,
        "traces_ingested": len(trace_ids),
        "trace_ids": trace_ids,
        "traces_processed": processed_count,
        "lessons_created": lesson_count,
        "lessons_retrieved": len(retrieved),
        "success": success,
    }

    status_label = "PASSED" if success else "FAILED"
    print(f"[cold_start] Scenario {status_label}")

    return result_summary
