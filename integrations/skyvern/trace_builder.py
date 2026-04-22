"""Map Skyvern response to Engram trace format."""

from __future__ import annotations

import uuid
from typing import Any

from skyvern.tasks import BrowserTask

ERROR_CATEGORIES = {
    "timed_out": "timeout",
    "failed": "execution_failure",
    "terminated": "execution_failure",
}


def build_trace(
    task: BrowserTask,
    skyvern_result: dict[str, Any],
    outcome: str,
    score: float,
    validation_details: dict[str, Any],
    retrieved_ids: list[str],
    detailed_steps: list[dict[str, Any]] | None = None,
    augmented_prompt: str | None = None,
) -> dict[str, Any]:
    """
    Build an Engram-compatible trace from a Skyvern task result.

    Returns a dict matching the Engram trace ingestion format.
    """
    skyvern_status = skyvern_result.get("status", "unknown")
    failure_reason = skyvern_result.get("failure_reason", "")
    steps = skyvern_result.get("steps", [])
    step_count = len(steps) if isinstance(steps, list) else 0

    # Build spans
    spans = []

    # Span 1: Lesson retrieval
    spans.append({
        "name": "retrieve_lessons",
        "status": "ok",
        "attributes": {
            "lesson_count": len(retrieved_ids),
            "lesson_ids": retrieved_ids,
        },
        "duration_ms": 100,
    })

    # Span 2: Skyvern execution (parent)
    exec_status = "ok" if outcome != "failure" else "error"
    exec_duration = _estimate_duration(skyvern_result)
    exec_attrs: dict[str, Any] = {
        "skyvern_status": skyvern_status,
        "url": task.url,
        "max_steps": task.max_steps,
        "steps_executed": step_count,
    }

    if outcome == "failure":
        error_category = _categorize_error(skyvern_status, failure_reason)
        error_signature = _build_error_signature(task, skyvern_status, failure_reason)
        exec_attrs["error_category"] = error_category
        exec_attrs["error_signature"] = error_signature
        exec_attrs["error"] = failure_reason or f"Task {skyvern_status}"

    spans.append({
        "name": "skyvern_execution",
        "status": exec_status,
        "attributes": exec_attrs,
        "duration_ms": exec_duration,
    })

    # Span 2.x: Per-step child spans
    step_spans = _build_step_spans(detailed_steps)
    spans.extend(step_spans)

    # Span 3: Validation
    val_status = "ok" if outcome == "success" else ("error" if outcome == "failure" else "warning")
    spans.append({
        "name": "validate_output",
        "status": val_status,
        "attributes": {
            "validation_mode": task.validation.mode,
            "score": score,
            "matched": validation_details.get("matched", 0),
            "total": validation_details.get("total", 0),
        },
        "duration_ms": 50,
    })

    trace_data: dict[str, Any] = {
        "agent": "skyvern-engram-v1",
        "task": task.title,
        "task_id": task.id,
        "url": task.url,
        "prompt": task.prompt,
        "skyvern_status": skyvern_status,
        "extracted_information": skyvern_result.get("extracted_information"),
        "retrieved_lesson_ids": retrieved_ids,
        "validation": {
            "outcome": outcome,
            "score": score,
            "details": validation_details,
        },
        "spans": spans,
        "result": {
            "task_passed": outcome == "success",
            "error": validation_details.get("reason") or validation_details.get("failure_reason"),
            "total_duration_ms": sum(s["duration_ms"] for s in spans),
            "steps_completed": step_count,
            "steps_total": task.max_steps,
        },
        "tags": task.tags,
        "run_id": str(uuid.uuid4()),
    }

    if augmented_prompt and augmented_prompt != task.prompt:
        trace_data["augmented_prompt"] = augmented_prompt

    return trace_data


def _categorize_error(status: str, failure_reason: str) -> str:
    """Categorize the error from Skyvern status and failure reason."""
    if status in ERROR_CATEGORIES:
        return ERROR_CATEGORIES[status]

    reason_lower = (failure_reason or "").lower()
    if "timeout" in reason_lower or "timed out" in reason_lower:
        return "timeout"
    if "navigation" in reason_lower or "navigate" in reason_lower:
        return "navigation_failure"
    if "extract" in reason_lower:
        return "extraction_failure"
    if "element" in reason_lower or "selector" in reason_lower or "not found" in reason_lower:
        return "element_not_found"
    return "unexpected_state"


def _build_error_signature(task: BrowserTask, status: str, failure_reason: str) -> str:
    """Build a dedup-friendly error signature."""
    category = _categorize_error(status, failure_reason)
    # Use task ID + category for grouping
    return f"{category}:{task.id}:{status}"


def _parse_step(step: dict[str, Any], index: int) -> dict[str, Any]:
    """Normalize a Skyvern step object into a span-friendly dict."""
    output = step.get("output", {}) or {}
    if isinstance(output, str):
        output = {"raw": output}

    # Extract action type from various possible locations
    action_type = (
        output.get("action_type")
        or step.get("action_type")
        or step.get("type")
        or "unknown"
    )

    # Extract action details
    actions = output.get("actions_and_results", output.get("actions", []))
    action_descriptions: list[str] = []
    element_descriptions: list[str] = []
    if isinstance(actions, list):
        for action in actions:
            if isinstance(action, dict):
                # actions_and_results entries may nest action under "action" key
                act = action.get("action", action)
                desc = act.get("reasoning") or act.get("description") or act.get("action_type", "")
                if desc:
                    action_descriptions.append(str(desc))
                elem = act.get("element_id") or act.get("selector") or act.get("element", "")
                if elem:
                    element_descriptions.append(str(elem))
                # If we don't have a good action_type yet, try from individual actions
                if action_type == "unknown":
                    action_type = act.get("action_type", "unknown")

    # Step-level error
    step_error = (
        step.get("failure_reason")
        or output.get("error")
        or output.get("failure_reason")
        or ""
    )

    # Step status
    step_status_raw = step.get("status", "unknown")
    step_ok = step_status_raw in ("completed", "success")

    # Duration from timestamps
    duration_ms = _step_duration(step)

    return {
        "action_type": action_type,
        "action_description": "; ".join(action_descriptions) if action_descriptions else "",
        "element_description": "; ".join(element_descriptions) if element_descriptions else "",
        "error": step_error,
        "status_ok": step_ok,
        "status_raw": step_status_raw,
        "duration_ms": duration_ms,
        "order": step.get("order", index),
        "step_id": step.get("step_id") or step.get("id", ""),
    }


def _step_duration(step: dict[str, Any]) -> int:
    """Calculate step duration from timestamps, or return a default."""
    created = step.get("created_at")
    updated = step.get("updated_at") or step.get("completed_at")
    if created and updated:
        try:
            from datetime import datetime

            t0 = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
            t1 = datetime.fromisoformat(str(updated).replace("Z", "+00:00"))
            ms = int((t1 - t0).total_seconds() * 1000)
            if ms > 0:
                return ms
        except (ValueError, TypeError):
            pass
    return 3000  # default 3s per step


def _build_step_spans(detailed_steps: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Build per-step child spans from detailed Skyvern step data."""
    if not detailed_steps:
        return []

    spans: list[dict[str, Any]] = []
    for i, raw_step in enumerate(detailed_steps):
        parsed = _parse_step(raw_step, i)

        action = parsed["action_type"]
        span_name = f"step_{i + 1}_{action}"

        attrs: dict[str, Any] = {
            "step_order": parsed["order"],
            "action_type": action,
        }
        if parsed["action_description"]:
            attrs["action_description"] = parsed["action_description"]
        if parsed["element_description"]:
            attrs["element_description"] = parsed["element_description"]
        if parsed["error"]:
            attrs["error"] = parsed["error"]
        if parsed["step_id"]:
            attrs["step_id"] = parsed["step_id"]
        # Include raw step data (truncated) for LLM extraction context
        attrs["step_data"] = _truncate_step_data(raw_step)

        spans.append({
            "name": span_name,
            "status": "ok" if parsed["status_ok"] else "error",
            "attributes": attrs,
            "duration_ms": parsed["duration_ms"],
            "parent": "skyvern_execution",
        })

    return spans


def _truncate_step_data(step: dict[str, Any], max_len: int = 1000) -> str:
    """Serialize step data for inclusion in span attributes, truncated."""
    import json

    try:
        raw = json.dumps(step, default=str)
    except (TypeError, ValueError):
        raw = str(step)
    if len(raw) > max_len:
        return raw[:max_len] + "..."
    return raw


def _estimate_duration(skyvern_result: dict[str, Any]) -> int:
    """Estimate execution duration from Skyvern result."""
    # Use created_at and completed_at if available
    created = skyvern_result.get("created_at")
    completed = skyvern_result.get("completed_at")
    if created and completed:
        try:
            from datetime import datetime

            t0 = datetime.fromisoformat(created.replace("Z", "+00:00"))
            t1 = datetime.fromisoformat(completed.replace("Z", "+00:00"))
            return max(int((t1 - t0).total_seconds() * 1000), 1000)
        except (ValueError, TypeError):
            pass
    # Default based on step count
    steps = skyvern_result.get("steps", [])
    return max(len(steps) * 5000, 5000)
