"""Failure cluster scenario: ingest grouped failures, trigger batch analysis, verify root_cause lesson."""

from pathlib import Path

from integrations.hercules.adapter import HerculesEngramAdapter
from integrations.shared.verify import (
    get_failure_queue_stats,
    trigger_batch_analysis,
    wait_for_lesson,
    wait_for_processing,
)


FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"

# 4 element-not-found failures with the same error pattern
ELEMENT_NOT_FOUND_FIXTURES = [
    FIXTURES_DIR / "failure_element_not_found_1.json",
    FIXTURES_DIR / "failure_element_not_found_2.json",
    FIXTURES_DIR / "failure_element_not_found_3.json",
    FIXTURES_DIR / "failure_element_not_found_4.json",
]


def run_failure_cluster(
    adapter: HerculesEngramAdapter,
    run_id: str,
) -> dict:
    """
    Run the failure cluster scenario:

    1. Ingest 4 element-not-found failure traces (same error pattern)
    2. Wait for traces to be processed and queued in the failure queue
    3. Check failure queue stats to confirm grouping
    4. Trigger batch analysis
    5. Verify a root_cause lesson was extracted from the cluster

    Args:
        adapter: Configured HerculesEngramAdapter instance.
        run_id: Unique run ID for dedup avoidance.

    Returns:
        Dict with trace_ids, queue_stats, analysis_result, and root_cause lessons.
    """
    print("\n=== Failure Cluster Scenario ===\n")

    # Step 1: Ingest failure traces
    trace_ids: list[str] = []
    for fixture_path in ELEMENT_NOT_FOUND_FIXTURES:
        trace_id = adapter.ingest_trace(fixture_path, run_id=run_id)
        trace_ids.append(trace_id)
        print(f"  Ingested failure trace: {trace_id} ({fixture_path.stem})")

    # Step 2: Wait for processing (failures go to failure queue, not lesson extraction)
    print("\n  Waiting for trace processing...")
    for trace_id in trace_ids:
        result = wait_for_processing(adapter.base_url, trace_id, timeout=90.0)
        status = result.get("status", "unknown") if result else "timeout"
        print(f"  Trace {trace_id}: {status}")

    # Step 3: Check failure queue stats
    print("\n  Checking failure queue stats...")
    stats = get_failure_queue_stats(adapter.base_url)
    pending = stats.get("pending", 0)
    by_signature = stats.get("by_signature", {})
    print(f"  Pending failures: {pending}")
    print(f"  Grouped by signature: {len(by_signature)} groups")
    for sig, count in by_signature.items():
        print(f"    {sig}: {count} traces")

    # Step 4: Trigger batch analysis
    print("\n  Triggering batch failure analysis...")
    analysis_result = trigger_batch_analysis(adapter.base_url)
    print(f"  Analysis result: {analysis_result}")

    # Step 5: Verify root_cause lesson was created
    print("\n  Checking for root_cause lessons...")
    root_cause_lessons = wait_for_lesson(
        adapter.base_url,
        agent_id=adapter.agent_id,
        lesson_type="root_cause",
        min_count=1,
        timeout=120.0,
    )
    print(f"  Found {len(root_cause_lessons)} root_cause lessons")
    for lesson in root_cause_lessons:
        content = lesson.get("lesson_text", lesson.get("content", ""))[:100]
        print(f"    - {content}...")

    return {
        "trace_ids": trace_ids,
        "queue_stats": stats,
        "analysis_result": analysis_result,
        "root_cause_lessons": root_cause_lessons,
        "root_cause_count": len(root_cause_lessons),
    }


if __name__ == "__main__":
    import os
    from integrations.shared.trace_builder import generate_run_id

    url = os.environ.get("ENGRAM_BASE_URL", "http://localhost:8000")
    with HerculesEngramAdapter(base_url=url) as adapter:
        result = run_failure_cluster(adapter, generate_run_id())
        print(f"\nFailure cluster complete. {result['root_cause_count']} root_cause lessons extracted.")
