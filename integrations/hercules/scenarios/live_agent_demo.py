"""Hercules Live Agent Demo — Tool Use + Deterministic Evaluation.

A standalone script where Claude acts as a test automation engineer, making
structured decisions via tool use. Choices are evaluated deterministically
against known page properties, creating real learnable failure modes.

Key insight: Claude defaults to CSS ID selectors and fixed timeouts, which
fail on React SPAs and slow staging environments. Tasks 5-6 repeat patterns
from Tasks 1-2, proving that lessons from early failures improve later rounds.

Usage:
    cd integrations
    ANTHROPIC_API_KEY=sk-ant-... uv run python -m hercules.scenarios.live_agent_demo

    # With seed lessons (skip cold start):
    ANTHROPIC_API_KEY=sk-ant-... uv run python -m hercules.scenarios.live_agent_demo --seed

Prerequisites:
    - Running Engram backend (API + Celery + Postgres + Redis)
    - ANTHROPIC_API_KEY env var set
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any

import anthropic
import httpx

from engram import EngramClient

AGENT_ID = "hercules-test-v1"
DOMAIN = "test-automation"
BASE_URL = os.environ.get("ENGRAM_BASE_URL", "http://localhost:8000")
MODEL = "claude-sonnet-4-5-20250929"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class PageEnvironment:
    """Ground truth about the page under test (hidden from Claude)."""

    dynamic_ids: bool = False
    has_iframe: bool = False
    has_shadow_dom: bool = False
    async_state_updates: bool = False
    slow_navigation: bool = False
    processing_time_ms: int = 0
    has_file_input: bool = False
    native_dialog: bool = False
    framework: str = "unknown"


@dataclass
class EvaluationRule:
    """A deterministic rule for scoring a strategy choice."""

    field: str  # StrategyChoice field to check
    condition: str  # "not_equals", "equals", "gte", "in"
    value: Any
    weight: float  # 0-1, contribution to score
    failure_reason: str


@dataclass
class TestTask:
    """A test automation scenario for the agent to handle."""

    title: str
    page_description: str  # What Claude sees (deliberately vague)
    action: str  # "click", "fill", "assert", "wait"
    target_element: str
    page_env: PageEnvironment
    rules: list[EvaluationRule]
    tags: list[str] = field(default_factory=list)


@dataclass
class StrategyChoice:
    """Parsed output from Claude's tool call."""

    selector_strategy: str
    selector_value: str
    wait_strategy: str
    wait_timeout_ms: int
    interaction_approach: str
    reasoning: str


# ---------------------------------------------------------------------------
# Tool definition for Claude
# ---------------------------------------------------------------------------

STRATEGY_TOOL = {
    "name": "choose_test_strategy",
    "description": (
        "Choose the test automation strategy for interacting with a web element. "
        "You must select a selector strategy, wait strategy, and interaction approach "
        "based on the page description and target element."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "selector_strategy": {
                "type": "string",
                "enum": [
                    "css_id",
                    "css_class",
                    "data_testid",
                    "data_attribute",
                    "aria_role",
                    "xpath",
                    "text_content",
                ],
                "description": "How to locate the element on the page.",
            },
            "selector_value": {
                "type": "string",
                "description": "The actual selector value (e.g., '#btn-submit', '[data-testid=\"add-cart\"]').",
            },
            "wait_strategy": {
                "type": "string",
                "enum": [
                    "fixed_timeout",
                    "network_idle",
                    "element_visible",
                    "text_change",
                    "url_change",
                    "dom_mutation",
                ],
                "description": "How to wait for the page/element to be ready.",
            },
            "wait_timeout_ms": {
                "type": "integer",
                "description": "Maximum time to wait in milliseconds.",
            },
            "interaction_approach": {
                "type": "string",
                "enum": [
                    "direct_click",
                    "frame_switch_then_interact",
                    "shadow_pierce",
                    "scroll_then_click",
                    "wait_then_assert",
                    "input_files_api",
                ],
                "description": "How to interact with the element.",
            },
            "reasoning": {
                "type": "string",
                "description": "Brief explanation of why you chose this strategy.",
            },
        },
        "required": [
            "selector_strategy",
            "selector_value",
            "wait_strategy",
            "wait_timeout_ms",
            "interaction_approach",
            "reasoning",
        ],
    },
}


# ---------------------------------------------------------------------------
# The 8 test tasks
# ---------------------------------------------------------------------------

TASKS: list[TestTask] = [
    # Task 1: Click add-to-cart on React page (dynamic IDs)
    TestTask(
        title="Click add-to-cart button on product detail page",
        page_description=(
            "A product detail page on an e-commerce site built with React. "
            "The page shows product images, description, price, and an 'Add to Cart' button. "
            "The site uses a modern component-based architecture."
        ),
        action="click",
        target_element="Add to Cart button",
        page_env=PageEnvironment(dynamic_ids=True, framework="react"),
        rules=[
            EvaluationRule(
                field="selector_strategy",
                condition="not_equals",
                value="css_id",
                weight=0.5,
                failure_reason="CSS ID selectors fail on React SPAs with dynamic IDs",
            ),
            EvaluationRule(
                field="selector_strategy",
                condition="in",
                value=["data_testid", "aria_role", "data_attribute", "text_content"],
                weight=0.3,
                failure_reason="Should use stable selectors (data-testid, aria, or text)",
            ),
            EvaluationRule(
                field="interaction_approach",
                condition="equals",
                value="direct_click",
                weight=0.2,
                failure_reason="Direct click is correct for a standard button",
            ),
        ],
        tags=["selectors", "dynamic-content", "react"],
    ),
    # Task 2: Wait for payment confirmation (slow staging)
    TestTask(
        title="Wait for payment confirmation on checkout page",
        page_description=(
            "A checkout confirmation page on a staging environment. After submitting payment, "
            "the page processes the transaction and shows a confirmation message. "
            "Note: this is a staging environment where backend services are slower than production. "
            "Payment processing involves multiple microservice calls."
        ),
        action="wait",
        target_element="Payment confirmation message ('Payment Successful')",
        page_env=PageEnvironment(
            slow_navigation=True, processing_time_ms=14000, framework="react"
        ),
        rules=[
            EvaluationRule(
                field="wait_strategy",
                condition="not_equals",
                value="fixed_timeout",
                weight=0.4,
                failure_reason="Fixed timeout is fragile — staging payment processing takes 14s+",
            ),
            EvaluationRule(
                field="wait_strategy",
                condition="in",
                value=["network_idle", "text_change", "element_visible"],
                weight=0.2,
                failure_reason="Should use an event-driven wait strategy",
            ),
            EvaluationRule(
                field="wait_timeout_ms",
                condition="gte",
                value=20000,
                weight=0.4,
                failure_reason="Timeout must be ≥20s (staging processing takes 14s, need margin)",
            ),
        ],
        tags=["timeouts", "staging", "slow-environment"],
    ),
    # Task 3: Fill credit card in Stripe iframe
    TestTask(
        title="Fill credit card number in checkout payment form",
        page_description=(
            "A checkout page with a payment form. The credit card fields "
            "(card number, expiration, CVC) are rendered by a third-party payment "
            "processor (Stripe). The payment fields appear visually integrated into "
            "the page but are actually in an embedded iframe."
        ),
        action="fill",
        target_element="Credit card number input field",
        page_env=PageEnvironment(has_iframe=True, framework="react"),
        rules=[
            EvaluationRule(
                field="interaction_approach",
                condition="equals",
                value="frame_switch_then_interact",
                weight=0.6,
                failure_reason="Must switch to iframe context to interact with Stripe elements",
            ),
            EvaluationRule(
                field="selector_strategy",
                condition="not_equals",
                value="css_id",
                weight=0.2,
                failure_reason="Stripe iframe elements don't have stable CSS IDs",
            ),
            EvaluationRule(
                field="wait_strategy",
                condition="not_equals",
                value="fixed_timeout",
                weight=0.2,
                failure_reason="Should wait for iframe to load, not use fixed timeout",
            ),
        ],
        tags=["iframes", "payment-forms", "stripe"],
    ),
    # Task 4: Assert cart badge after adding item (async state)
    TestTask(
        title="Assert cart badge count updates after adding item",
        page_description=(
            "After clicking 'Add to Cart', verify that the cart icon badge in the "
            "navigation bar updates to show the new item count. The site is a React "
            "single-page application where state updates trigger re-renders. "
            "The cart count is managed by a global state store (Redux/Zustand)."
        ),
        action="assert",
        target_element="Cart badge count in navigation bar",
        page_env=PageEnvironment(
            async_state_updates=True, dynamic_ids=True, framework="react"
        ),
        rules=[
            EvaluationRule(
                field="wait_strategy",
                condition="in",
                value=["text_change", "dom_mutation", "network_idle"],
                weight=0.5,
                failure_reason="Must wait for async state update before asserting",
            ),
            EvaluationRule(
                field="wait_strategy",
                condition="not_equals",
                value="fixed_timeout",
                weight=0.2,
                failure_reason="Fixed timeout creates race conditions with async state updates",
            ),
            EvaluationRule(
                field="interaction_approach",
                condition="equals",
                value="wait_then_assert",
                weight=0.3,
                failure_reason="Should wait for state change, then assert — not direct click",
            ),
        ],
        tags=["assertions", "async", "state-management"],
    ),
    # Task 5: Click reviews tab on React page (REPEAT of Task 1 pattern)
    TestTask(
        title="Click 'Customer Reviews' tab on product page",
        page_description=(
            "A product page on a React-based e-commerce platform. The page has "
            "multiple tabs: Description, Specifications, Customer Reviews, Q&A. "
            "You need to click the 'Customer Reviews' tab to show the reviews section. "
            "The site uses a modern component-based architecture with dynamic rendering."
        ),
        action="click",
        target_element="Customer Reviews tab",
        page_env=PageEnvironment(dynamic_ids=True, framework="react"),
        rules=[
            EvaluationRule(
                field="selector_strategy",
                condition="not_equals",
                value="css_id",
                weight=0.5,
                failure_reason="CSS ID selectors fail on React SPAs with dynamic IDs",
            ),
            EvaluationRule(
                field="selector_strategy",
                condition="in",
                value=["data_testid", "aria_role", "data_attribute", "text_content"],
                weight=0.3,
                failure_reason="Should use stable selectors (data-testid, aria, or text)",
            ),
            EvaluationRule(
                field="interaction_approach",
                condition="equals",
                value="direct_click",
                weight=0.2,
                failure_reason="Direct click is correct for a tab element",
            ),
        ],
        tags=["selectors", "dynamic-content", "react", "learning-check"],
    ),
    # Task 6: Wait for PDF report generation (REPEAT of Task 2 pattern)
    TestTask(
        title="Wait for PDF report to generate and download link to appear",
        page_description=(
            "An admin dashboard on a staging environment. After clicking 'Generate Report', "
            "the system compiles data across multiple services and generates a PDF. "
            "A download link appears when the report is ready. "
            "Note: this is a staging environment where report generation is significantly "
            "slower than production due to limited resources."
        ),
        action="wait",
        target_element="Download PDF link",
        page_env=PageEnvironment(
            slow_navigation=True, processing_time_ms=25000, framework="react"
        ),
        rules=[
            EvaluationRule(
                field="wait_strategy",
                condition="not_equals",
                value="fixed_timeout",
                weight=0.4,
                failure_reason="Fixed timeout fails — report generation takes 25s on staging",
            ),
            EvaluationRule(
                field="wait_strategy",
                condition="in",
                value=["network_idle", "element_visible", "dom_mutation"],
                weight=0.2,
                failure_reason="Should use event-driven wait for the download link to appear",
            ),
            EvaluationRule(
                field="wait_timeout_ms",
                condition="gte",
                value=30000,
                weight=0.4,
                failure_reason="Timeout must be ≥30s (staging report gen takes 25s, need margin)",
            ),
        ],
        tags=["timeouts", "staging", "slow-environment", "learning-check"],
    ),
    # Task 7: Click accept on shadow DOM cookie banner
    TestTask(
        title="Click 'Accept All' on cookie consent banner",
        page_description=(
            "A website with a cookie consent banner at the bottom of the page. "
            "The banner is implemented as a web component using Shadow DOM. "
            "The 'Accept All' button is inside the shadow root of a "
            "<cookie-consent> custom element. Standard selectors cannot reach "
            "inside the shadow boundary."
        ),
        action="click",
        target_element="Accept All button inside shadow DOM cookie banner",
        page_env=PageEnvironment(has_shadow_dom=True, framework="web-components"),
        rules=[
            EvaluationRule(
                field="interaction_approach",
                condition="equals",
                value="shadow_pierce",
                weight=0.6,
                failure_reason="Must pierce shadow DOM boundary to reach the button",
            ),
            EvaluationRule(
                field="selector_strategy",
                condition="not_equals",
                value="css_id",
                weight=0.2,
                failure_reason="CSS IDs don't cross shadow DOM boundaries",
            ),
            EvaluationRule(
                field="wait_strategy",
                condition="not_equals",
                value="fixed_timeout",
                weight=0.2,
                failure_reason="Should wait for shadow DOM component to render",
            ),
        ],
        tags=["shadow-dom", "web-components", "cookie-consent"],
    ),
    # Task 8: Upload profile avatar (native file dialog)
    TestTask(
        title="Upload a profile avatar image",
        page_description=(
            "A user profile settings page with an avatar upload section. "
            "There's an 'Upload Photo' button that, when clicked, opens the "
            "operating system's native file selection dialog. The page has a "
            "hidden <input type='file'> element connected to the visible button."
        ),
        action="click",
        target_element="Upload Photo button / file input",
        page_env=PageEnvironment(
            has_file_input=True, native_dialog=True, framework="react"
        ),
        rules=[
            EvaluationRule(
                field="interaction_approach",
                condition="equals",
                value="input_files_api",
                weight=0.6,
                failure_reason="Must use setInputFiles API — native OS dialogs can't be automated",
            ),
            EvaluationRule(
                field="interaction_approach",
                condition="not_equals",
                value="direct_click",
                weight=0.2,
                failure_reason="Direct click opens native dialog which blocks automation",
            ),
            EvaluationRule(
                field="selector_strategy",
                condition="in",
                value=["css_class", "data_testid", "data_attribute", "xpath", "css_id"],
                weight=0.2,
                failure_reason="Need to target the hidden <input type='file'> element",
            ),
        ],
        tags=["file-upload", "native-dialogs"],
    ),
]


# ---------------------------------------------------------------------------
# Evaluation engine
# ---------------------------------------------------------------------------


def evaluate_choice(
    choice: StrategyChoice, rules: list[EvaluationRule]
) -> tuple[str, float, list[str]]:
    """
    Evaluate a strategy choice against deterministic rules.

    Returns:
        (outcome, score, failed_reasons)
    """
    total_weight = sum(r.weight for r in rules)
    earned_weight = 0.0
    failed_reasons: list[str] = []

    for rule in rules:
        field_value = getattr(choice, rule.field, None)
        passed = False

        if rule.condition == "equals":
            passed = field_value == rule.value
        elif rule.condition == "not_equals":
            passed = field_value != rule.value
        elif rule.condition == "gte":
            passed = isinstance(field_value, (int, float)) and field_value >= rule.value
        elif rule.condition == "in":
            passed = field_value in rule.value

        if passed:
            earned_weight += rule.weight
        else:
            failed_reasons.append(
                f"{rule.failure_reason} (chose {rule.field}={field_value!r})"
            )

    score = round(earned_weight / total_weight, 2) if total_weight > 0 else 0.0

    if score >= 0.8:
        outcome = "success"
    elif score >= 0.4:
        outcome = "partial"
    else:
        outcome = "failure"

    return outcome, score, failed_reasons


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are Hercules, an expert test automation engineer. Your job is to choose \
the optimal strategy for interacting with web elements during automated tests.

For each task, you will receive:
- A description of the page and its technology stack
- The target element you need to interact with
- The action to perform (click, fill, assert, wait)

You must call the choose_test_strategy tool with your decisions. Consider:
- Selector stability: IDs can be dynamic in SPAs, data-testid is most stable
- Wait strategies: Fixed timeouts are fragile, prefer event-driven waits
- Interaction context: Iframes need frame switching, shadow DOM needs piercing
- Environment: Staging environments are slower than production

Choose carefully — wrong strategies cause flaky tests."""


def build_prompt_with_lessons(
    task: TestTask,
    lessons: list[dict[str, Any]],
) -> str:
    """Build system prompt with retrieved lessons."""
    parts = [SYSTEM_PROMPT]

    if lessons:
        parts.append(
            "\n\n--- LESSONS FROM PAST TEST RUNS ---\n"
            "These are lessons learned from previous test automation attempts. "
            "Apply what worked and avoid mistakes that were identified."
        )
        for i, lesson in enumerate(lessons, 1):
            text = lesson.get("lesson_text", lesson.get("content", ""))
            outcome = lesson.get("outcome", "unknown")
            utility = lesson.get("utility", 0.5)
            parts.append(
                f"\nLesson {i} (outcome: {outcome}, utility: {utility:.2f}):\n{text}"
            )

    return "\n".join(parts)


def build_task_message(task: TestTask) -> str:
    """Build the user message describing the task."""
    return (
        f"**Task:** {task.title}\n\n"
        f"**Page:** {task.page_description}\n\n"
        f"**Action:** {task.action}\n\n"
        f"**Target element:** {task.target_element}\n\n"
        f"Choose your test automation strategy by calling the choose_test_strategy tool."
    )


# ---------------------------------------------------------------------------
# Trace building
# ---------------------------------------------------------------------------


def build_trace(
    task: TestTask,
    choice: StrategyChoice,
    outcome: str,
    score: float,
    failed_reasons: list[str],
    retrieved_ids: list[str],
) -> dict[str, Any]:
    """Build a trace matching the Hercules fixture format."""
    select_status = "ok" if outcome == "success" else "error"
    select_attrs: dict[str, Any] = {
        "selector": choice.selector_value,
        "strategy": choice.selector_strategy,
    }
    if outcome != "success":
        # Add error info for failed selections
        if "selector" in " ".join(failed_reasons).lower():
            select_attrs["error_category"] = "element_not_found"
            select_attrs["error_signature"] = (
                f"element_not_found:{choice.selector_strategy}:{choice.selector_value}"
            )
            select_attrs["error"] = (
                f"ElementNotFoundError: Strategy '{choice.selector_strategy}' "
                f"failed on this page"
            )
        elif "timeout" in " ".join(failed_reasons).lower():
            select_attrs["error_category"] = "timeout"
            select_attrs["error_signature"] = (
                f"timeout:{choice.wait_strategy}:{choice.wait_timeout_ms}ms"
            )
            select_attrs["error"] = (
                f"TimeoutError: Wait strategy '{choice.wait_strategy}' "
                f"timed out after {choice.wait_timeout_ms}ms"
            )
        elif "iframe" in " ".join(failed_reasons).lower() or "frame" in " ".join(
            failed_reasons
        ).lower():
            select_attrs["error_category"] = "iframe_context"
            select_attrs["error_signature"] = (
                f"iframe_context:{choice.interaction_approach}"
            )
            select_attrs["error"] = (
                "ContextError: Element is inside an iframe but no frame switch was performed"
            )
        elif "shadow" in " ".join(failed_reasons).lower():
            select_attrs["error_category"] = "shadow_dom"
            select_attrs["error_signature"] = (
                f"shadow_dom:{choice.interaction_approach}"
            )
            select_attrs["error"] = (
                "ShadowDOMError: Element is inside shadow DOM boundary"
            )
        elif "native" in " ".join(failed_reasons).lower() or "file" in " ".join(
            failed_reasons
        ).lower():
            select_attrs["error_category"] = "native_dialog"
            select_attrs["error_signature"] = (
                f"native_dialog:{choice.interaction_approach}"
            )
            select_attrs["error"] = (
                "NativeDialogError: Clicked button opened native OS file dialog"
            )
        else:
            select_attrs["error_category"] = "strategy_mismatch"
            select_attrs["error_signature"] = f"strategy_mismatch:{task.action}"
            select_attrs["error"] = f"StrategyError: Suboptimal strategy for {task.action}"

    spans = [
        {
            "name": "navigate",
            "status": "ok",
            "attributes": {"url": "/simulated-page", "load_time_ms": 1100},
            "duration_ms": 1100,
        },
        {
            "name": "select_element",
            "status": select_status,
            "attributes": select_attrs,
            "duration_ms": choice.wait_timeout_ms if select_status == "error" else 200,
        },
        {
            "name": "wait",
            "status": "ok" if outcome != "failure" else "error",
            "attributes": {
                "strategy": choice.wait_strategy,
                "timeout_ms": choice.wait_timeout_ms,
            },
            "duration_ms": min(choice.wait_timeout_ms, 5000),
        },
        {
            "name": "interact",
            "status": "ok" if outcome == "success" else select_status,
            "attributes": {
                "approach": choice.interaction_approach,
                "action": task.action,
            },
            "duration_ms": 300,
        },
    ]

    return {
        "agent": AGENT_ID,
        "task": task.title,
        "test_target": "simulated",
        "browser": "chromium",
        "page_framework": task.page_env.framework,
        "strategy_chosen": {
            "selector_strategy": choice.selector_strategy,
            "selector_value": choice.selector_value,
            "wait_strategy": choice.wait_strategy,
            "wait_timeout_ms": choice.wait_timeout_ms,
            "interaction_approach": choice.interaction_approach,
            "reasoning": choice.reasoning,
        },
        "evaluation": {
            "score": score,
            "outcome": outcome,
            "failed_reasons": failed_reasons,
        },
        "retrieved_lesson_ids": retrieved_ids,
        "spans": spans,
        "result": {
            "test_passed": outcome == "success",
            "error": "; ".join(failed_reasons) if failed_reasons else None,
            "total_duration_ms": sum(s["duration_ms"] for s in spans),
            "steps_completed": sum(1 for s in spans if s["status"] == "ok"),
            "steps_total": len(spans),
        },
        "tags": task.tags,
    }


# ---------------------------------------------------------------------------
# Core task execution
# ---------------------------------------------------------------------------


def run_task(
    task: TestTask,
    round_num: int,
    total_rounds: int,
    engram: EngramClient,
    claude: anthropic.Anthropic,
) -> dict[str, Any]:
    """Execute a single test task through the full learn-retrieve-improve loop."""
    is_learning_check = "learning-check" in task.tags
    label = " [LEARNING CHECK]" if is_learning_check else ""
    print(f"\n{'='*60}")
    print(f"[Task {round_num}/{total_rounds}] {task.title}{label}")
    print(f"{'='*60}")

    # Step 1: Retrieve lessons
    retrieve_context = f"{task.page_description} {task.target_element} {task.action}"
    try:
        result = engram.retrieve(
            context=retrieve_context,
            domain=DOMAIN,
            top_k=5,
            min_confidence=0.1,
        )
        retrieved_lessons = [l.model_dump() for l in result.lessons]
    except Exception as e:
        print(f"  Warning: Retrieval failed ({e}), proceeding without lessons")
        retrieved_lessons = []

    lesson_count = len(retrieved_lessons)
    retrieved_ids = [l["id"] for l in retrieved_lessons]
    if lesson_count > 0:
        avg_utility = sum(l.get("utility", 0.5) for l in retrieved_lessons) / lesson_count
        print(f"  Retrieved {lesson_count} lessons (avg utility: {avg_utility:.2f})")
        for l in retrieved_lessons:
            text = l.get("lesson_text", l.get("content", ""))[:80]
            print(f"    - {text}...")
    else:
        avg_utility = 0.0
        print("  No lessons retrieved (cold start)")

    # Step 2: Build prompt with lessons
    system = build_prompt_with_lessons(task, retrieved_lessons)
    user_message = build_task_message(task)

    # Step 3: Call Claude API with tool use
    try:
        response = claude.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": user_message}],
            tools=[STRATEGY_TOOL],
            tool_choice={"type": "tool", "name": "choose_test_strategy"},
        )
    except Exception as e:
        print(f"  ERROR: Claude API call failed: {e}")
        return {"error": str(e), "outcome": "failure", "score": 0.0}

    # Parse tool call response
    tool_input = None
    for block in response.content:
        if block.type == "tool_use" and block.name == "choose_test_strategy":
            tool_input = block.input
            break

    if not tool_input:
        print("  ERROR: Claude did not call the tool")
        return {"error": "no_tool_call", "outcome": "failure", "score": 0.0}

    choice = StrategyChoice(
        selector_strategy=tool_input["selector_strategy"],
        selector_value=tool_input["selector_value"],
        wait_strategy=tool_input["wait_strategy"],
        wait_timeout_ms=tool_input["wait_timeout_ms"],
        interaction_approach=tool_input["interaction_approach"],
        reasoning=tool_input["reasoning"],
    )

    print(f"\n  Strategy chosen:")
    print(f"    Selector:    {choice.selector_strategy} → {choice.selector_value}")
    print(f"    Wait:        {choice.wait_strategy} ({choice.wait_timeout_ms}ms)")
    print(f"    Interaction: {choice.interaction_approach}")
    print(f"    Reasoning:   {choice.reasoning[:100]}...")

    # Step 4: Evaluate deterministically
    outcome, score, failed_reasons = evaluate_choice(choice, task.rules)

    outcome_icons = {"success": "✓", "partial": "~", "failure": "✗"}
    icon = outcome_icons.get(outcome, "?")
    print(f"\n  [{icon}] Outcome: {outcome} (score: {score})")
    if failed_reasons:
        for reason in failed_reasons:
            print(f"      ✗ {reason}")
    else:
        print("      All rules passed!")

    # Step 5: Build and ingest trace
    trace_data = build_trace(
        task, choice, outcome, score, failed_reasons, retrieved_ids
    )

    trace_id = None
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

    # Step 6: Report outcome
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
        "choice": {
            "selector_strategy": choice.selector_strategy,
            "wait_strategy": choice.wait_strategy,
            "wait_timeout_ms": choice.wait_timeout_ms,
            "interaction_approach": choice.interaction_approach,
        },
        "failed_reasons": failed_reasons,
        "is_learning_check": is_learning_check,
        "tags": task.tags,
    }


# ---------------------------------------------------------------------------
# Seed lessons
# ---------------------------------------------------------------------------


def maybe_seed_lessons(engram: EngramClient, force_seed: bool = False) -> int:
    """Optionally seed lessons. Returns count of existing lessons."""
    try:
        result = engram.retrieve(
            context="test automation selectors",
            domain=DOMAIN,
            top_k=1,
            min_confidence=0.0,
        )
        existing = result.total
        if existing > 0 and not force_seed:
            return existing
    except Exception:
        existing = 0

    if not force_seed:
        print("  Memory pool is empty — starting cold (no seed lessons)")
        return 0

    print("  Seeding initial lessons...")
    try:
        from hercules.seed_lessons import seed

        created = seed(BASE_URL)
        count = len(created)
        if count > 0:
            print(f"  Seeded {count} lessons, waiting for embeddings...")
            time.sleep(5)
        return count
    except Exception as e:
        print(f"  Warning: Seeding failed ({e}), continuing without seed lessons")
        return 0


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


def print_summary(results: list[dict[str, Any]]) -> None:
    """Print a detailed summary with learning analysis."""
    print("\n" + "=" * 60)
    print("  RESULTS SUMMARY")
    print("=" * 60)

    outcomes = {"success": 0, "failure": 0, "partial": 0}
    total_score = 0.0
    total_retrieved = 0

    for r in results:
        outcome = r.get("outcome", "failure")
        outcomes[outcome] = outcomes.get(outcome, 0) + 1
        total_score += r.get("score", 0.0)
        total_retrieved += r.get("lessons_retrieved", 0)

    n = len(results)
    print(f"\n  Tasks run:        {n}")
    print(
        f"  Outcomes:         "
        f"{outcomes['success']} success, "
        f"{outcomes['partial']} partial, "
        f"{outcomes['failure']} failure"
    )
    print(f"  Average score:    {total_score / n:.2f}")
    print(f"  Total retrievals: {total_retrieved}")

    # Per-task breakdown
    print(f"\n  {'Task':<55} {'Score':>6} {'Outcome':>8} {'Lessons':>8}")
    print(f"  {'-'*55} {'-'*6} {'-'*8} {'-'*8}")
    for r in results:
        title = r["task"][:53]
        check = " *" if r.get("is_learning_check") else ""
        score = r.get("score", 0.0)
        outcome = r.get("outcome", "?")
        lessons = r.get("lessons_retrieved", 0)
        print(f"  {title + check:<55} {score:>6.2f} {outcome:>8} {lessons:>8}")

    # Learning analysis — compare paired tasks
    print("\n  LEARNING ANALYSIS")
    print("  " + "-" * 50)

    pairs = [
        (0, 4, "Selectors (React dynamic IDs)"),
        (1, 5, "Timeouts (slow staging)"),
    ]

    learning_detected = False
    for first, second, pattern in pairs:
        if first < n and second < n:
            s1 = results[first].get("score", 0.0)
            s2 = results[second].get("score", 0.0)
            delta = s2 - s1
            arrow = "↑" if delta > 0 else "↓" if delta < 0 else "→"
            improved = delta > 0

            print(f"\n  {pattern}:")
            print(f"    Task {first+1}: {s1:.2f}  →  Task {second+1}: {s2:.2f}  ({arrow} {delta:+.2f})")

            c1 = results[first].get("choice", {})
            c2 = results[second].get("choice", {})

            if pattern.startswith("Selectors"):
                print(f"    Selector: {c1.get('selector_strategy', '?')} → {c2.get('selector_strategy', '?')}")
            elif pattern.startswith("Timeouts"):
                print(f"    Wait: {c1.get('wait_strategy', '?')} → {c2.get('wait_strategy', '?')}")
                print(f"    Timeout: {c1.get('wait_timeout_ms', '?')}ms → {c2.get('wait_timeout_ms', '?')}ms")

            if improved:
                learning_detected = True
                print(f"    ✓ LEARNING DETECTED — score improved!")
            elif delta == 0 and s1 >= 0.8:
                print(f"    ✓ Already correct on first attempt")
            else:
                print(f"    ✗ No improvement detected")

    if learning_detected:
        print(f"\n  ✓ DEMO SUCCESS: Agent learned from early failures and improved!")
    else:
        print(f"\n  ~ Learning signal may need more rounds or seed lessons.")
        print(f"    Try running with --seed flag for comparison.")

    print("\n  Check the Engram dashboard for traces and extracted lessons.")
    print("=" * 60)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run_demo(seed: bool = False) -> None:
    """Run the full Hercules live agent demo."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY environment variable is required")
        sys.exit(1)

    print("=" * 60)
    print("  Hercules Live Agent Demo")
    print("  Tool Use + Deterministic Evaluation")
    print("=" * 60)

    engram = EngramClient(base_url=BASE_URL, agent_id=AGENT_ID)
    claude_client = anthropic.Anthropic(api_key=api_key)

    mode = "with seed lessons" if seed else "cold start (no seeds)"
    print(f"\n  Backend:  {BASE_URL}")
    print(f"  Agent:    {AGENT_ID}")
    print(f"  Model:    {MODEL}")
    print(f"  Tasks:    {len(TASKS)}")
    print(f"  Mode:     {mode}")

    # Health check
    try:
        resp = httpx.get(f"{BASE_URL}/health", timeout=5.0)
        resp.raise_for_status()
        print("  Backend:  healthy")
    except Exception as e:
        print(f"\n  ERROR: Backend not reachable at {BASE_URL}: {e}")
        print("  Make sure docker compose up -d and uvicorn are running.")
        sys.exit(1)

    # Seed if requested
    print("\nChecking memory pool...")
    existing = maybe_seed_lessons(engram, force_seed=seed)
    print(f"  Lessons available: {existing}")

    # Run all tasks
    results: list[dict[str, Any]] = []
    for i, task in enumerate(TASKS, 1):
        result = run_task(task, i, len(TASKS), engram, claude_client)
        results.append(result)
        # Wait between tasks for Celery to extract lessons and generate embeddings
        if i < len(TASKS):
            wait = 3
            print(f"\n  Waiting {wait}s for lesson extraction...")
            time.sleep(wait)

    print_summary(results)
    engram.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Hercules Live Agent Demo — Tool Use + Deterministic Evaluation"
    )
    parser.add_argument(
        "--seed",
        action="store_true",
        help="Seed initial lessons before running (skip cold start)",
    )
    args = parser.parse_args()
    run_demo(seed=args.seed)


if __name__ == "__main__":
    main()
