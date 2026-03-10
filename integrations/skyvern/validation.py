"""Validate Skyvern task results against expected data."""

from __future__ import annotations

from typing import Any

from skyvern.tasks import BrowserTask


def validate_result(
    task: BrowserTask,
    skyvern_result: dict[str, Any],
) -> tuple[str, float, dict[str, Any]]:
    """
    Validate a Skyvern task result against the task's validation spec.

    Returns:
        (outcome, score, details) where:
        - outcome: "success" | "partial" | "failure"
        - score: 0.0 to 1.0
        - details: dict with validation details
    """
    status = skyvern_result.get("status", "unknown")
    details: dict[str, Any] = {"skyvern_status": status}

    # Check Skyvern-level failure
    if status in ("failed", "timed_out", "terminated"):
        details["reason"] = f"Skyvern task {status}"
        failure_reason = skyvern_result.get("failure_reason", "")
        if failure_reason:
            details["failure_reason"] = failure_reason
        return "failure", 0.0, details

    # Status-only validation — any non-failure status is success
    if task.validation.mode == "status_only":
        if status in ("completed",):
            return "success", 1.0, details
        return "partial", 0.5, details

    # Data extraction validation
    if task.validation.mode == "data_extraction":
        extracted = skyvern_result.get("extracted_information") or {}
        expected = task.validation.expected_data or {}

        if not expected:
            # No expected data — just check that something was extracted
            if extracted:
                return "success", 1.0, {**details, "extracted": extracted}
            return "partial", 0.5, {**details, "extracted": extracted}

        matched = 0
        total = len(expected)
        match_details: dict[str, Any] = {}

        for key, expected_val in expected.items():
            actual_val = extracted.get(key)
            if _values_match(expected_val, actual_val):
                matched += 1
                match_details[key] = {"expected": expected_val, "actual": actual_val, "match": True}
            else:
                match_details[key] = {"expected": expected_val, "actual": actual_val, "match": False}

        score = matched / total if total > 0 else 0.0
        details["match_details"] = match_details
        details["matched"] = matched
        details["total"] = total
        details["extracted"] = extracted

        if score >= 0.75:
            return "success", round(score, 2), details
        elif score >= 0.4:
            return "partial", round(score, 2), details
        else:
            return "failure", round(score, 2), details

    # Unknown validation mode
    details["reason"] = f"Unknown validation mode: {task.validation.mode}"
    return "partial", 0.5, details


def _values_match(expected: Any, actual: Any) -> bool:
    """Check if actual value matches expected, with loose string matching."""
    if actual is None:
        return False

    # Boolean comparison
    if isinstance(expected, bool):
        if isinstance(actual, bool):
            return actual == expected
        if isinstance(actual, str):
            return actual.lower() in ("true", "yes", "1") if expected else actual.lower() in ("false", "no", "0")
        return bool(actual) == expected

    # Integer comparison
    if isinstance(expected, int):
        if isinstance(actual, int):
            return actual == expected
        if isinstance(actual, str):
            try:
                return int(actual) == expected
            except ValueError:
                return False
        return False

    # String comparison — case-insensitive partial match
    if isinstance(expected, str):
        actual_str = str(actual).strip().lower()
        expected_str = expected.strip().lower()
        return expected_str in actual_str or actual_str in expected_str

    return expected == actual
