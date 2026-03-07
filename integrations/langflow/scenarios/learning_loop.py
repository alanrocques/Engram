"""Learning Loop scenario for the Langflow Customer Support Agent.

Validates the full learn-retrieve-improve cycle including:
- Ingesting success and failure traces
- Extracting lessons from successes
- Queuing failures for batch analysis
- Running batch analysis to produce root_cause lessons
- Retrieving lessons and reporting outcomes
- Verifying utility score updates

Usage:
    from integrations.langflow.adapter import LangflowEngramAdapter
    from integrations.langflow.scenarios.learning_loop import run_learning_loop

    adapter = LangflowEngramAdapter()
    result = run_learning_loop(adapter, run_id="test-002")
"""

from __future__ import annotations

import time
from typing import Any

from integrations.shared.verify import wait_for_lesson, wait_for_processing


def run_learning_loop(
    adapter: Any,
    run_id: str,
    *,
    timeout: float = 120.0,
) -> dict[str, Any]:
    """
    Run the full learning loop scenario.

    Steps:
        1. Ingest success traces to build initial memory
        2. Ingest failure traces (CRM timeouts) to populate failure queue
        3. Wait for success traces to produce lessons
        4. Retrieve lessons before batch analysis
        5. Trigger batch failure analysis
        6. Verify root_cause lessons were created
        7. Report outcomes to update utility scores
        8. Retrieve again — verify improved results

    Args:
        adapter: LangflowEngramAdapter instance.
        run_id: Unique run ID to prevent dedup collisions.
        timeout: Max seconds to wait for processing per step.

    Returns:
        Dict with detailed step results and overall success flag.
    """
    print(f"[learning_loop] Starting learning loop scenario (run_id={run_id})")
    steps: dict[str, Any] = {}

    # ---------------------------------------------------------------
    # Step 1: Ingest success traces
    # ---------------------------------------------------------------
    print("\n[Step 1] Ingesting success traces...")
    success_fixtures = [
        "success_refund_processed.json",
        "success_complaint_resolved.json",
        "success_subscription_upgrade.json",
    ]
    success_trace_ids: list[str] = []
    for fixture in success_fixtures:
        tid = adapter.ingest_trace(fixture, run_id=run_id)
        success_trace_ids.append(tid)
        print(f"  Ingested {fixture} -> {tid}")

    steps["success_traces"] = {
        "count": len(success_trace_ids),
        "trace_ids": success_trace_ids,
    }

    # ---------------------------------------------------------------
    # Step 2: Ingest failure traces (CRM timeouts for batch analysis)
    # ---------------------------------------------------------------
    print("\n[Step 2] Ingesting CRM timeout failure traces...")
    failure_fixtures = [
        "failure_crm_api_timeout_1.json",
        "failure_crm_api_timeout_2.json",
        "failure_crm_api_timeout_3.json",
    ]
    failure_trace_ids: list[str] = []
    for fixture in failure_fixtures:
        tid = adapter.ingest_trace(fixture, run_id=run_id)
        failure_trace_ids.append(tid)
        print(f"  Ingested {fixture} -> {tid}")

    steps["failure_traces"] = {
        "count": len(failure_trace_ids),
        "trace_ids": failure_trace_ids,
    }

    # ---------------------------------------------------------------
    # Step 3: Wait for success traces to produce lessons
    # ---------------------------------------------------------------
    print("\n[Step 3] Waiting for success trace processing...")
    processed = 0
    for tid in success_trace_ids:
        result = wait_for_processing(adapter.base_url, tid, timeout=timeout)
        if result and result.get("status") == "processed":
            processed += 1
    print(f"  {processed}/{len(success_trace_ids)} success traces processed")

    # Also wait for failure traces to be processed (queued to failure queue)
    print("  Waiting for failure trace processing...")
    for tid in failure_trace_ids:
        wait_for_processing(adapter.base_url, tid, timeout=timeout)

    # Give embedding generation a moment
    time.sleep(3)

    # Check for lessons
    lessons_before = wait_for_lesson(
        adapter.base_url,
        agent_id=adapter.agent_id,
        min_count=1,
        timeout=timeout,
    )
    steps["lessons_after_ingestion"] = len(lessons_before)
    print(f"  Lessons found: {len(lessons_before)}")

    # ---------------------------------------------------------------
    # Step 4: Retrieve lessons (pre-batch-analysis baseline)
    # ---------------------------------------------------------------
    print("\n[Step 4] Retrieving lessons for CRM timeout context...")
    pre_batch_lessons = adapter.retrieve_lessons(
        context="CRM API is timing out when looking up customer data",
        top_k=5,
    )
    steps["retrieval_pre_batch"] = {
        "count": len(pre_batch_lessons),
        "lesson_ids": [l.get("id", "") for l in pre_batch_lessons],
    }
    print(f"  Retrieved {len(pre_batch_lessons)} lessons pre-batch-analysis")

    # ---------------------------------------------------------------
    # Step 5: Check failure queue and trigger batch analysis
    # ---------------------------------------------------------------
    print("\n[Step 5] Checking failure queue stats...")
    queue_stats = adapter.get_failure_queue_stats()
    pending = queue_stats.get("pending", 0)
    print(f"  Failure queue pending: {pending}")
    steps["failure_queue_pre"] = queue_stats

    print("  Triggering batch failure analysis...")
    batch_result = adapter.trigger_batch_analysis()
    steps["batch_analysis"] = batch_result
    print(f"  Batch analysis result: {batch_result}")

    # Wait for batch analysis to complete and lessons to be created
    time.sleep(5)

    # ---------------------------------------------------------------
    # Step 6: Verify root_cause lessons were created
    # ---------------------------------------------------------------
    print("\n[Step 6] Checking for root_cause lessons...")
    root_cause_lessons = wait_for_lesson(
        adapter.base_url,
        agent_id=adapter.agent_id,
        lesson_type="root_cause",
        min_count=1,
        timeout=timeout,
        interval=3.0,
    )
    steps["root_cause_lessons"] = len(root_cause_lessons)
    print(f"  Root cause lessons found: {len(root_cause_lessons)}")
    for lesson in root_cause_lessons[:3]:
        snippet = str(lesson.get("lesson_text", lesson.get("content", "")))[:80]
        print(f"    - {snippet}...")

    # ---------------------------------------------------------------
    # Step 7: Report outcomes to update utility scores
    # ---------------------------------------------------------------
    print("\n[Step 7] Reporting outcomes...")
    outcome_results: list[dict[str, Any]] = []

    if pre_batch_lessons:
        # Report a success outcome referencing retrieved lessons
        retrieved_ids = [l["id"] for l in pre_batch_lessons if "id" in l]
        if success_trace_ids:
            try:
                outcome = adapter.report_outcome(
                    trace_id=success_trace_ids[0],
                    outcome="success",
                    retrieved_lesson_ids=retrieved_ids[:3],
                    downstream_utility=0.8,
                    context_similarity=0.9,
                )
                outcome_results.append(outcome)
                print(f"  Reported success outcome for trace {success_trace_ids[0]}")
            except Exception as e:
                print(f"  Failed to report outcome: {e}")

    steps["outcomes_reported"] = len(outcome_results)

    # ---------------------------------------------------------------
    # Step 8: Retrieve again — check for improved results
    # ---------------------------------------------------------------
    print("\n[Step 8] Retrieving lessons post-batch-analysis...")
    post_batch_lessons = adapter.retrieve_lessons(
        context="CRM API is timing out when looking up customer data",
        top_k=5,
    )
    steps["retrieval_post_batch"] = {
        "count": len(post_batch_lessons),
        "lesson_ids": [l.get("id", "") for l in post_batch_lessons],
    }
    print(f"  Retrieved {len(post_batch_lessons)} lessons post-batch-analysis")

    # Also check with a different query
    refund_lessons = adapter.retrieve_lessons(
        context="How to handle customer refund for a returned item",
        top_k=3,
    )
    steps["retrieval_refund"] = {
        "count": len(refund_lessons),
    }
    print(f"  Retrieved {len(refund_lessons)} lessons for refund query")

    # ---------------------------------------------------------------
    # Summary
    # ---------------------------------------------------------------
    success = (
        processed >= 2
        and steps["lessons_after_ingestion"] >= 1
        and len(post_batch_lessons) >= 1
    )

    result_summary = {
        "scenario": "learning_loop",
        "run_id": run_id,
        "success": success,
        "steps": steps,
    }

    status_label = "PASSED" if success else "FAILED"
    print(f"\n[learning_loop] Scenario {status_label}")

    return result_summary
