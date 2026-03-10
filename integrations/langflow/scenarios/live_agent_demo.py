"""Live Agent Demo — Prove the Learn-Retrieve-Improve Loop.

A standalone script that runs a customer support agent using the Claude API
+ Engram SDK, demonstrating the full learning loop:

  1. Retrieve relevant lessons from Engram
  2. Build a prompt with lessons as context
  3. Call Claude API for a decision
  4. Evaluate the response quality
  5. Ingest the trace and report the outcome
  6. Repeat — later rounds benefit from earlier lessons

This is the reference implementation for anyone building framework integrations.

Usage:
    cd integrations
    ANTHROPIC_API_KEY=sk-ant-... python -m langflow.scenarios.live_agent_demo

Prerequisites:
    - Running Engram backend (API + Celery + Postgres + Redis)
    - ANTHROPIC_API_KEY env var set
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any

import anthropic
import httpx

from engram import EngramClient

AGENT_ID = "live-demo-support-v1"
DOMAIN = "customer-support"
BASE_URL = os.environ.get("ENGRAM_BASE_URL", "http://localhost:8000")
MODEL = "claude-sonnet-4-5-20250929"


# ---------------------------------------------------------------------------
# Support tasks — designed so repeated themes demonstrate learning
# ---------------------------------------------------------------------------

@dataclass
class SupportTask:
    """A customer support scenario for the agent to handle."""

    title: str
    customer_message: str
    required_elements: list[str]
    tags: list[str] = field(default_factory=list)


SUPPORT_TASKS: list[SupportTask] = [
    SupportTask(
        title="Refund for damaged item (order #ORD-1234)",
        customer_message=(
            "Hi, I received my order #ORD-1234 yesterday and the ceramic vase "
            "arrived completely shattered. The packaging was inadequate — just a "
            "thin layer of bubble wrap. I want a full refund immediately."
        ),
        required_elements=[
            "empathy",       # Acknowledge frustration
            "apology",       # Say sorry
            "refund_action", # Offer/initiate refund
            "timeline",      # Set expectations for when
        ],
        tags=["refund", "damaged-item"],
    ),
    SupportTask(
        title="International warranty coverage question",
        customer_message=(
            "I bought a laptop from your US store but I live in Germany. "
            "The screen started flickering after 4 months. Does my warranty "
            "cover international repairs? Where do I send it?"
        ),
        required_elements=[
            "warranty_info",     # Address warranty coverage
            "international",     # Mention international policy
            "next_steps",        # Clear action items
        ],
        tags=["warranty", "international"],
    ),
    SupportTask(
        title="Subscription downgrade with data concerns",
        customer_message=(
            "I want to downgrade from Business to Personal plan. But I have "
            "15 team members and 200GB of shared files. What happens to our "
            "data and team access when I downgrade?"
        ),
        required_elements=[
            "data_impact",       # Explain what happens to data
            "feature_loss",      # List features they'll lose
            "migration_steps",   # How to preserve data
            "timeline",          # When changes take effect
        ],
        tags=["subscription", "downgrade", "data-migration"],
    ),
    SupportTask(
        title="Second refund request — wrong size clothing",
        customer_message=(
            "Order #ORD-5678 — I ordered a Medium t-shirt but received a Large. "
            "I'd like a refund or exchange. The item is unworn with tags attached. "
            "This is the second time I've had a sizing issue with your store."
        ),
        required_elements=[
            "empathy",           # Acknowledge repeat issue
            "apology",           # Sorry for inconvenience
            "refund_action",     # Process refund/exchange
            "prevention",        # Address recurring issue
        ],
        tags=["refund", "wrong-item", "repeat-issue"],
    ),
    SupportTask(
        title="Angry customer — order delayed 3 weeks",
        customer_message=(
            "THIS IS UNACCEPTABLE. I ordered a birthday gift THREE WEEKS AGO "
            "and it still hasn't arrived. The birthday was LAST WEEK. Your "
            "tracking page just says 'in transit'. I want my money back AND "
            "compensation for ruining my daughter's birthday."
        ),
        required_elements=[
            "empathy",           # De-escalation
            "apology",           # Sincere apology
            "investigation",     # Look into the delay
            "compensation",      # Offer something beyond refund
            "escalation_offer",  # Offer to escalate if needed
        ],
        tags=["complaint", "shipping-delay", "angry-customer"],
    ),
    SupportTask(
        title="Third refund — defective electronics",
        customer_message=(
            "My wireless earbuds (order #ORD-9012) stopped working after just "
            "2 weeks. The left earbud won't charge. I've already tried the "
            "troubleshooting steps on your website. I need a refund — I don't "
            "want a replacement because I've lost confidence in the product."
        ),
        required_elements=[
            "empathy",            # Understand frustration
            "apology",            # Apologize for defect
            "refund_action",      # Process refund (not replacement)
            "quality_assurance",  # Mention quality feedback
        ],
        tags=["refund", "defective", "electronics"],
    ),
]


# ---------------------------------------------------------------------------
# Response evaluation — rule-based scoring
# ---------------------------------------------------------------------------

# Keywords that indicate each required element is present
ELEMENT_KEYWORDS: dict[str, list[str]] = {
    "empathy": ["understand", "frustrat", "sorry to hear", "appreciate", "must be"],
    "apology": ["apologize", "sorry", "apologies", "regret"],
    "refund_action": ["refund", "reimburse", "credit", "money back", "process"],
    "timeline": ["within", "business days", "hours", "expect", "shortly", "immediately"],
    "warranty_info": ["warranty", "covered", "coverage", "guarantee", "protection"],
    "international": ["international", "country", "region", "global", "overseas", "germany"],
    "next_steps": ["next step", "here's what", "you can", "please", "follow", "send"],
    "data_impact": ["data", "files", "storage", "access", "lose", "preserved", "deleted"],
    "feature_loss": ["feature", "functionality", "access", "team member", "limit", "lose"],
    "migration_steps": ["export", "download", "backup", "migrate", "transfer", "save"],
    "prevention": ["prevent", "ensure", "future", "quality", "sizing guide", "improve"],
    "investigation": ["investigate", "look into", "check", "track", "status", "find out"],
    "compensation": ["compensat", "credit", "discount", "coupon", "gesture", "goodwill"],
    "escalation_offer": ["escalat", "manager", "supervisor", "team", "specialist", "priority"],
    "quality_assurance": ["quality", "feedback", "team", "improve", "report", "aware"],
    "refund_action": ["refund", "reimburse", "credit", "money back", "process"],
}


def evaluate_response(
    response_text: str,
    required_elements: list[str],
) -> tuple[str, float, list[str], list[str]]:
    """
    Score the agent response based on required elements.

    Returns:
        (outcome, score, elements_found, elements_missing)
    """
    response_lower = response_text.lower()
    found: list[str] = []
    missing: list[str] = []

    for element in required_elements:
        keywords = ELEMENT_KEYWORDS.get(element, [])
        if any(kw in response_lower for kw in keywords):
            found.append(element)
        else:
            missing.append(element)

    score = len(found) / len(required_elements) if required_elements else 0.0

    if score >= 0.75:
        outcome = "success"
    elif score >= 0.4:
        outcome = "partial"
    else:
        outcome = "failure"

    return outcome, round(score, 2), found, missing


# ---------------------------------------------------------------------------
# System prompt for the support agent
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a customer support agent for an e-commerce company. Your job is to \
help customers with their issues professionally, empathetically, and efficiently.

Guidelines:
- Always acknowledge the customer's feelings
- Apologize sincerely when appropriate
- Provide clear action steps with timelines
- Offer compensation for serious issues
- Be specific about policies (refund windows, warranty terms, etc.)
- If unsure about a policy, say so honestly rather than guessing

Keep your response concise (under 300 words). Address the customer directly."""


def build_prompt_with_lessons(
    task: SupportTask,
    lessons: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """Build Claude API messages with retrieved lessons as context."""
    system_parts = [SYSTEM_PROMPT]

    if lessons:
        system_parts.append("\n\n--- PAST EXPERIENCE (lessons from previous interactions) ---")
        for i, lesson in enumerate(lessons, 1):
            text = lesson.get("lesson_text", lesson.get("content", ""))
            outcome = lesson.get("outcome", "unknown")
            utility = lesson.get("utility", 0.5)
            system_parts.append(
                f"\nLesson {i} (outcome: {outcome}, utility: {utility:.2f}):\n{text}"
            )
        system_parts.append(
            "\n\nUse these lessons to inform your response. "
            "Apply what worked before and avoid past mistakes."
        )

    return [
        {"role": "user", "content": task.customer_message},
    ], "\n".join(system_parts)


# ---------------------------------------------------------------------------
# Core task execution
# ---------------------------------------------------------------------------

def run_task(
    task: SupportTask,
    round_num: int,
    total_rounds: int,
    engram: EngramClient,
    claude: anthropic.Anthropic,
) -> dict[str, Any]:
    """Execute a single support task through the full learn-retrieve-improve loop."""
    print(f"\n[Round {round_num}/{total_rounds}] Task: {task.title}")

    # Step 1: Retrieve lessons
    try:
        result = engram.retrieve(
            context=task.customer_message,
            domain=DOMAIN,
            top_k=5,
            min_confidence=0.1,
        )
        retrieved_lessons = [l.model_dump() for l in result.lessons]
    except Exception as e:
        print(f"  Warning: Retrieval failed ({e}), proceeding without lessons")
        retrieved_lessons = []

    lesson_count = len(retrieved_lessons)
    if lesson_count > 0:
        avg_utility = sum(l.get("utility", 0.5) for l in retrieved_lessons) / lesson_count
        print(f"  Retrieved {lesson_count} lessons (avg utility: {avg_utility:.2f})")
    else:
        avg_utility = 0.0
        print("  Retrieved 0 lessons (no prior experience)")

    # Step 2: Build prompt with lessons
    messages, system = build_prompt_with_lessons(task, retrieved_lessons)

    # Step 3: Call Claude API
    try:
        response = claude.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=system,
            messages=messages,
        )
        agent_response = response.content[0].text
    except Exception as e:
        print(f"  ERROR: Claude API call failed: {e}")
        return {"error": str(e), "outcome": "failure", "score": 0.0}

    truncated = agent_response[:80].replace("\n", " ")
    print(f"  Agent response: \"{truncated}...\" ({len(agent_response)} chars)")

    # Step 4: Evaluate response
    outcome, score, found, missing = evaluate_response(
        agent_response, task.required_elements
    )

    outcome_icons = {"success": "OK", "partial": "WARN", "failure": "FAIL"}
    icon = outcome_icons.get(outcome, "?")
    print(f"  [{icon}] Outcome: {outcome} (score: {score})")
    if missing:
        print(f"       Missing: {', '.join(missing)}")

    # Step 5: Ingest trace
    retrieved_ids = [l["id"] for l in retrieved_lessons]
    trace_data = {
        "task": task.title,
        "customer_message": task.customer_message,
        "agent_response": agent_response,
        "outcome": outcome,
        "score": score,
        "elements_found": found,
        "elements_missing": missing,
        "lessons_retrieved": lesson_count,
        "tags": task.tags,
        "spans": [
            {
                "name": "retrieve_lessons",
                "status": "ok",
                "attributes": {
                    "lesson_count": lesson_count,
                    "lesson_ids": retrieved_ids,
                },
            },
            {
                "name": "call_claude_api",
                "status": "ok",
                "attributes": {
                    "model": MODEL,
                    "response_length": len(agent_response),
                },
            },
            {
                "name": "evaluate_response",
                "status": "ok" if outcome == "success" else "error",
                "attributes": {
                    "outcome": outcome,
                    "score": score,
                    "elements_found": found,
                    "elements_missing": missing,
                },
            },
        ],
    }

    try:
        trace_result = engram.ingest_trace(
            trace_data=trace_data,
            process_async=True,
            outcome=outcome,
        )
        trace_id = trace_result.id
        print(f"  Trace ingested: {trace_id}")
    except Exception as e:
        print(f"  Warning: Trace ingestion failed ({e})")
        trace_id = None

    # Step 6: Report outcome with retrieved lesson IDs
    updated_count = 0
    if trace_id and retrieved_ids:
        try:
            outcome_result = engram.report_outcome(
                trace_id=trace_id,
                outcome=outcome,
                retrieved_lesson_ids=retrieved_ids,
                downstream_utility=score,
                context_similarity=avg_utility,
            )
            updated_count = outcome_result.updated_count
            print(f"  Updated {updated_count} lesson utilities")
        except Exception as e:
            print(f"  Warning: Outcome reporting failed ({e})")

    return {
        "task": task.title,
        "outcome": outcome,
        "score": score,
        "lessons_retrieved": lesson_count,
        "avg_utility": avg_utility,
        "trace_id": trace_id,
        "lessons_updated": updated_count,
        "elements_found": found,
        "elements_missing": missing,
    }


# ---------------------------------------------------------------------------
# Seed lessons if the DB is empty
# ---------------------------------------------------------------------------

def maybe_seed_lessons(engram: EngramClient) -> int:
    """Seed initial lessons if the memory pool is empty. Returns count of existing lessons."""
    try:
        result = engram.retrieve(
            context="customer support",
            top_k=1,
            min_confidence=0.0,
        )
        if result.lessons:
            return result.total
    except Exception:
        pass

    print("  Memory pool is empty — seeding initial lessons...")
    try:
        from langflow.seed_lessons import seed
        created = seed(BASE_URL)
        count = len(created)
        # Give embeddings time to generate
        if count > 0:
            print(f"  Seeded {count} lessons, waiting for embeddings...")
            time.sleep(5)
        return count
    except Exception as e:
        print(f"  Warning: Seeding failed ({e}), continuing without seed lessons")
        return 0


# ---------------------------------------------------------------------------
# Main demo
# ---------------------------------------------------------------------------

def run_demo() -> None:
    """Run the full live agent demo."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY environment variable is required")
        sys.exit(1)

    print("=" * 60)
    print("  Engram Live Agent Demo")
    print("  Learn-Retrieve-Improve Loop")
    print("=" * 60)

    # Initialize clients
    engram = EngramClient(base_url=BASE_URL, agent_id=AGENT_ID)
    claude_client = anthropic.Anthropic(api_key=api_key)

    print(f"\n  Backend: {BASE_URL}")
    print(f"  Agent:   {AGENT_ID}")
    print(f"  Model:   {MODEL}")
    print(f"  Tasks:   {len(SUPPORT_TASKS)}")

    # Check backend health
    try:
        resp = httpx.get(f"{BASE_URL}/health", timeout=5.0)
        resp.raise_for_status()
        print("  Backend: healthy")
    except Exception as e:
        print(f"\n  ERROR: Backend not reachable at {BASE_URL}: {e}")
        print("  Make sure docker compose up -d and uvicorn are running.")
        sys.exit(1)

    # Seed lessons if needed
    print("\nChecking memory pool...")
    existing = maybe_seed_lessons(engram)
    print(f"  Lessons available: {existing}")

    # Run all tasks
    results: list[dict[str, Any]] = []
    for i, task in enumerate(SUPPORT_TASKS, 1):
        result = run_task(task, i, len(SUPPORT_TASKS), engram, claude_client)
        results.append(result)
        # Small delay between tasks to let Celery process traces
        if i < len(SUPPORT_TASKS):
            time.sleep(2)

    # Print summary
    print("\n" + "=" * 60)
    print("  Summary")
    print("=" * 60)

    outcomes = {"success": 0, "failure": 0, "partial": 0}
    total_score = 0.0
    total_retrieved = 0
    total_updated = 0

    for r in results:
        outcome = r.get("outcome", "failure")
        outcomes[outcome] = outcomes.get(outcome, 0) + 1
        total_score += r.get("score", 0.0)
        total_retrieved += r.get("lessons_retrieved", 0)
        total_updated += r.get("lessons_updated", 0)

    print(f"\n  Tasks run:         {len(results)}")
    print(
        f"  Outcomes:          "
        f"{outcomes['success']} success, "
        f"{outcomes['partial']} partial, "
        f"{outcomes['failure']} failure"
    )
    print(f"  Average score:     {total_score / len(results):.2f}")
    print(f"  Total retrievals:  {total_retrieved} lessons across all rounds")
    print(f"  Utility updates:   {total_updated} lessons updated")

    # Show per-round retrieval growth
    print("\n  Per-round retrieval:")
    for i, r in enumerate(results, 1):
        count = r.get("lessons_retrieved", 0)
        score = r.get("score", 0.0)
        bar = "#" * int(score * 20)
        print(f"    Round {i}: {count} lessons retrieved | score {score:.2f} |{bar}|")

    print("\n  Done. Check the Engram dashboard for new lessons and traces.")
    print("=" * 60)

    engram.close()


if __name__ == "__main__":
    run_demo()
