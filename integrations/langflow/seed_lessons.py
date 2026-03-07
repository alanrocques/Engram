"""Seed initial lessons for the Langflow Customer Support Agent integration.

Seeds 5-8 domain-specific lessons that provide a baseline memory pool
before any traces are ingested. Run this before integration tests to
avoid the cold-start problem.

Usage:
    python -m integrations.langflow.seed_lessons
    ENGRAM_BASE_URL=http://localhost:8000 python -m integrations.langflow.seed_lessons
"""

import os
import sys

import httpx

AGENT_ID = "langflow-support-v1"
DOMAIN = "customer-support"
BASE_URL = os.environ.get("ENGRAM_BASE_URL", "http://localhost:8000")

SEED_LESSONS = [
    {
        "agent_id": AGENT_ID,
        "task_context": "Processing customer refund requests",
        "action_taken": "Check refund eligibility by verifying order status, return window (30 days from delivery), and item condition before initiating the refund through the payment gateway.",
        "outcome": "success",
        "lesson_text": "Always verify refund eligibility (return window + item condition) before calling the payment API. Skipping eligibility checks leads to rejected refunds and angry customers who thought the refund was processed.",
        "tags": ["refund", "eligibility", "payment", "best-practice"],
        "domain": DOMAIN,
    },
    {
        "agent_id": AGENT_ID,
        "task_context": "Handling CRM API timeouts during customer lookups",
        "action_taken": "Implemented retry with exponential backoff (3 retries, 1s/2s/4s delays) when CRM API calls time out.",
        "outcome": "success",
        "lesson_text": "CRM API timeouts are common during peak hours (10am-2pm EST). Use exponential backoff with 3 retries. If all retries fail, offer the customer a callback rather than making them wait — this preserves satisfaction scores.",
        "tags": ["crm", "timeout", "retry", "resilience"],
        "domain": DOMAIN,
    },
    {
        "agent_id": AGENT_ID,
        "task_context": "Detecting and routing angry customers appropriately",
        "action_taken": "Applied sentiment analysis before composing response, switching to empathetic tone template when negative sentiment detected.",
        "outcome": "success",
        "lesson_text": "When sentiment analysis confidence is below 0.6, default to empathetic tone rather than casual. Misclassifying an angry customer as neutral leads to immediate escalation requests and negative CSAT scores.",
        "tags": ["sentiment", "tone", "escalation", "response-quality"],
        "domain": DOMAIN,
    },
    {
        "agent_id": AGENT_ID,
        "task_context": "Handling multi-issue customer complaints",
        "action_taken": "Classified each issue by complexity, auto-resolved simple issues (billing errors, shipping delays), and escalated complex issues (product defects) to specialist teams.",
        "outcome": "partial",
        "lesson_text": "For multi-issue complaints, resolve the simple issues immediately and escalate the complex ones. Customers prefer partial resolution now over waiting for everything to be resolved together. Always communicate what was resolved vs. what is pending.",
        "tags": ["complaint", "multi-issue", "escalation", "triage"],
        "domain": DOMAIN,
    },
    {
        "agent_id": AGENT_ID,
        "task_context": "Providing product recommendations to new customers",
        "action_taken": "Attempted personalized recommendations with collaborative filtering, fell back to category bestsellers when purchase history was insufficient.",
        "outcome": "partial",
        "lesson_text": "New customers with fewer than 3 orders should get category-based bestsellers instead of collaborative filtering. The personalization algorithm needs at least 3 diverse purchases to produce useful recommendations. Add a disclaimer when using fallback recommendations.",
        "tags": ["recommendation", "cold-start", "personalization", "fallback"],
        "domain": DOMAIN,
    },
    {
        "agent_id": AGENT_ID,
        "task_context": "Processing subscription changes (upgrades, downgrades, cancellations)",
        "action_taken": "Checked feature compatibility before processing downgrade, warned customer about data loss for incompatible features, and exported data before disabling features.",
        "outcome": "success",
        "lesson_text": "Before processing any subscription downgrade, always check feature compatibility and warn about data loss. Export customer data for incompatible features BEFORE disabling them. Customers who lose data without warning file complaints 4x more often.",
        "tags": ["subscription", "downgrade", "data-migration", "feature-compatibility"],
        "domain": DOMAIN,
    },
    {
        "agent_id": AGENT_ID,
        "task_context": "Creating support tickets without duplicates",
        "action_taken": "Searched for existing tickets by order ID and issue type before creating a new ticket.",
        "outcome": "failure",
        "lesson_text": "Ticket dedup search must match on both order ID AND issue description similarity (not just exact order ID match). Fuzzy matching on issue description catches duplicates where customers describe the same problem in different words.",
        "tags": ["ticket", "dedup", "search", "data-integrity"],
        "domain": DOMAIN,
    },
]


def seed(base_url: str = BASE_URL) -> list[dict]:
    """Seed initial lessons and return the created lesson responses."""
    client = httpx.Client(
        base_url=f"{base_url.rstrip('/')}/api/v1",
        timeout=30.0,
        headers={"Content-Type": "application/json"},
    )
    created = []
    try:
        for lesson in SEED_LESSONS:
            resp = client.post("/lessons", json=lesson)
            if resp.status_code in (200, 201):
                data = resp.json()
                print(f"  Created lesson {data.get('id', '?')}: {lesson['task_context'][:60]}...")
                created.append(data)
            elif resp.status_code == 409:
                print(f"  Skipped (duplicate): {lesson['task_context'][:60]}...")
            else:
                print(f"  FAILED ({resp.status_code}): {lesson['task_context'][:60]}...")
                print(f"    Response: {resp.text[:200]}")
    finally:
        client.close()

    print(f"\nSeeded {len(created)} lessons for agent '{AGENT_ID}'")
    return created


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else BASE_URL
    print(f"Seeding lessons to {url}...")
    seed(url)
