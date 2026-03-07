"""Cold start scenario: ingest a few success traces, verify lessons are extracted and retrievable."""

from pathlib import Path

from integrations.hercules.adapter import HerculesEngramAdapter
from integrations.shared.verify import wait_for_lesson, wait_for_processing


FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"

# The 3 success fixtures used for cold start
COLD_START_FIXTURES = [
    FIXTURES_DIR / "success_login_flow.json",
    FIXTURES_DIR / "success_search_products.json",
    FIXTURES_DIR / "success_form_submission.json",
]


def run_cold_start(
    adapter: HerculesEngramAdapter,
    run_id: str,
) -> dict:
    """
    Run the cold start scenario:

    1. Ingest 3 success traces
    2. Wait for each trace to be processed (lesson extraction)
    3. Verify that at least 3 success_pattern lessons exist
    4. Retrieve lessons for a related context and verify relevance

    Args:
        adapter: Configured HerculesEngramAdapter instance.
        run_id: Unique run ID for dedup avoidance.

    Returns:
        Dict with trace_ids, lesson_ids, and retrieval results.
    """
    print("\n=== Cold Start Scenario ===\n")

    # Step 1: Ingest success traces
    trace_ids: list[str] = []
    for fixture_path in COLD_START_FIXTURES:
        trace_id = adapter.ingest_trace(fixture_path, run_id=run_id)
        trace_ids.append(trace_id)
        print(f"  Ingested trace: {trace_id} ({fixture_path.stem})")

    # Step 2: Wait for processing
    print("\n  Waiting for trace processing...")
    for trace_id in trace_ids:
        result = wait_for_processing(adapter.base_url, trace_id, timeout=90.0)
        status = result.get("status", "unknown") if result else "timeout"
        print(f"  Trace {trace_id}: {status}")

    # Step 3: Verify lessons were created
    print("\n  Checking for extracted lessons...")
    lessons = wait_for_lesson(
        adapter.base_url,
        agent_id=adapter.agent_id,
        lesson_type="success_pattern",
        min_count=3,
        timeout=90.0,
    )
    print(f"  Found {len(lessons)} success_pattern lessons")
    lesson_ids = [l["id"] for l in lessons]

    # Step 4: Retrieve lessons for a related context
    print("\n  Testing retrieval for related context...")
    retrieval_results = adapter.retrieve_lessons(
        context="automate login form test with username and password fields",
        top_k=5,
    )
    print(f"  Retrieved {len(retrieval_results)} lessons")
    for i, lesson in enumerate(retrieval_results):
        content = lesson.get("lesson_text", lesson.get("content", ""))[:80]
        print(f"    {i + 1}. {content}...")

    return {
        "trace_ids": trace_ids,
        "lesson_ids": lesson_ids,
        "lessons_found": len(lessons),
        "retrieval_results": retrieval_results,
    }


if __name__ == "__main__":
    import os
    from integrations.shared.trace_builder import generate_run_id

    url = os.environ.get("ENGRAM_BASE_URL", "http://localhost:8000")
    with HerculesEngramAdapter(base_url=url) as adapter:
        result = run_cold_start(adapter, generate_run_id())
        print(f"\nCold start complete. {result['lessons_found']} lessons extracted.")
