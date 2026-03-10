"""SkyvernEngramWrapper — core orchestrator for the retrieve-augment-execute loop."""

from __future__ import annotations

import time
from typing import Any

import httpx

from engram import EngramClient

from skyvern.config import SkyvernConfig
from skyvern.tasks import BrowserTask, LEARNING_PAIRS
from skyvern.trace_builder import build_trace
from skyvern.validation import validate_result


class SkyvernEngramWrapper:
    """Orchestrate the Engram retrieve -> augment -> Skyvern execute -> capture loop."""

    def __init__(self, config: SkyvernConfig) -> None:
        self.config = config
        self.engram = EngramClient(
            base_url=config.engram_base_url,
            agent_id=config.agent_id,
        )
        self._skyvern = httpx.Client(
            base_url=config.skyvern_base_url.rstrip("/"),
            timeout=30.0,
            headers={
                "x-api-key": config.skyvern_api_key,
                "Content-Type": "application/json",
            },
        )

    # ------------------------------------------------------------------
    # Prompt augmentation
    # ------------------------------------------------------------------

    def _augment_prompt(self, base_prompt: str, lessons: list[dict[str, Any]]) -> str:
        """Prepend retrieved lessons to the task prompt."""
        if not lessons:
            return base_prompt
        parts = ["IMPORTANT - Lessons from past attempts:\n"]
        for i, lesson in enumerate(lessons, 1):
            text = lesson.get("lesson_text", lesson.get("content", ""))
            outcome = lesson.get("outcome", "unknown")
            parts.append(f"{i}. [{outcome.upper()}] {text}")
        parts.append("\nNow proceed with the task:\n")
        parts.append(base_prompt)
        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Skyvern API interaction
    # ------------------------------------------------------------------

    def _create_skyvern_task(self, task: BrowserTask, augmented_prompt: str) -> dict[str, Any]:
        """Create a task via the Skyvern API."""
        payload: dict[str, Any] = {
            "url": task.url,
            "navigation_goal": augmented_prompt,
            "max_steps_override": task.max_steps,
        }
        if task.validation.mode == "data_extraction" and task.validation.data_extraction_schema:
            payload["data_extraction_goal"] = (
                f"Extract the following data from the page: "
                f"{', '.join(task.validation.data_extraction_schema.get('properties', {}).keys())}"
            )
            payload["extracted_information_schema"] = task.validation.data_extraction_schema

        response = self._skyvern.post("/api/v1/tasks", json=payload)
        response.raise_for_status()
        return response.json()

    def _fetch_task_steps(self, task_id: str) -> list[dict[str, Any]]:
        """Fetch detailed step data from Skyvern."""
        try:
            response = self._skyvern.get(f"/api/v1/tasks/{task_id}/steps")
            response.raise_for_status()
            data = response.json()
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _poll_skyvern_task(self, task_id: str) -> dict[str, Any]:
        """Poll Skyvern until the task completes."""
        deadline = time.time() + self.config.skyvern_poll_timeout
        while time.time() < deadline:
            response = self._skyvern.get(f"/api/v1/tasks/{task_id}")
            response.raise_for_status()
            data = response.json()
            status = data.get("status", "unknown")
            if status in ("completed", "failed", "timed_out", "terminated"):
                return data
            time.sleep(self.config.skyvern_poll_interval)
        return {"status": "timed_out", "failure_reason": "Engram poll timeout exceeded"}

    # ------------------------------------------------------------------
    # Core loop
    # ------------------------------------------------------------------

    def run_task(self, task: BrowserTask, task_num: int, total: int) -> dict[str, Any]:
        """Run a single task through the full Engram loop."""
        is_learning_check = "learning-check" in task.tags
        label = " [LEARNING CHECK]" if is_learning_check else ""
        print(f"\n{'=' * 60}")
        print(f"[Task {task_num}/{total}] {task.title}{label}")
        print(f"  URL: {task.url}")
        print(f"{'=' * 60}")

        # 1. Retrieve lessons
        retrieve_context = f"{task.title} {task.prompt[:200]} {' '.join(task.tags)}"
        retrieved_lessons: list[dict[str, Any]] = []
        retrieved_ids: list[str] = []
        avg_utility = 0.0

        try:
            # Don't filter by domain — LLM extraction assigns varied domains
            # (web-scraping, web-automation, authentication, etc.) that won't
            # match our static config domain. Agent ID filtering is sufficient.
            result = self.engram.retrieve(
                context=retrieve_context,
                top_k=5,
                min_confidence=0.1,
            )
            retrieved_lessons = [l.model_dump() for l in result.lessons]
            retrieved_ids = [l["id"] for l in retrieved_lessons]
        except Exception as e:
            print(f"  Warning: Retrieval failed ({e}), proceeding without lessons")

        if retrieved_lessons:
            avg_utility = sum(l.get("utility", 0.5) for l in retrieved_lessons) / len(retrieved_lessons)
            print(f"  Retrieved {len(retrieved_lessons)} lessons (avg utility: {avg_utility:.2f})")
            for l in retrieved_lessons:
                text = l.get("lesson_text", l.get("content", ""))[:80]
                print(f"    - {text}...")
        else:
            print("  No lessons retrieved (cold start)")

        # 2. Augment prompt
        augmented_prompt = self._augment_prompt(task.prompt, retrieved_lessons)

        # 3. Execute via Skyvern
        print(f"\n  Sending task to Skyvern...")
        detailed_steps: list[dict[str, Any]] = []
        try:
            created = self._create_skyvern_task(task, augmented_prompt)
            skyvern_task_id = created.get("task_id") or created.get("id", "unknown")
            print(f"  Skyvern task created: {skyvern_task_id}")
            print(f"  Polling for completion (timeout: {self.config.skyvern_poll_timeout}s)...")
            skyvern_result = self._poll_skyvern_task(skyvern_task_id)

            # Fetch detailed step data for richer trace spans
            detailed_steps = self._fetch_task_steps(skyvern_task_id)
            if detailed_steps:
                print(f"  Fetched {len(detailed_steps)} detailed steps")
        except Exception as e:
            print(f"  ERROR: Skyvern execution failed: {e}")
            skyvern_result = {"status": "failed", "failure_reason": str(e)}

        skyvern_status = skyvern_result.get("status", "unknown")
        print(f"  Skyvern status: {skyvern_status}")

        extracted = skyvern_result.get("extracted_information")
        if extracted:
            print(f"  Extracted data: {extracted}")

        # 4. Validate result
        outcome, score, details = validate_result(task, skyvern_result)

        outcome_icons = {"success": "OK", "partial": "~~", "failure": "XX"}
        icon = outcome_icons.get(outcome, "??")
        print(f"\n  [{icon}] Outcome: {outcome} (score: {score})")
        if details.get("match_details"):
            for key, info in details["match_details"].items():
                match_str = "OK" if info["match"] else "MISS"
                print(f"      {match_str} {key}: expected={info['expected']!r} got={info['actual']!r}")

        # 5. Ingest trace
        trace_data = build_trace(
            task, skyvern_result, outcome, score, details, retrieved_ids,
            detailed_steps=detailed_steps or None,
        )
        trace_id = None
        try:
            trace_result = self.engram.ingest_trace(
                trace_data=trace_data,
                process_async=True,
                outcome=outcome,
            )
            trace_id = trace_result.id
            print(f"  Trace ingested: {trace_id}")
        except Exception as e:
            print(f"  Warning: Trace ingestion failed ({e})")

        # 6. Report outcome
        updated_count = 0
        if trace_id and retrieved_ids:
            try:
                outcome_result = self.engram.report_outcome(
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
            "task_id": task.id,
            "task": task.title,
            "outcome": outcome,
            "score": score,
            "lessons_retrieved": len(retrieved_lessons),
            "avg_utility": avg_utility,
            "trace_id": trace_id,
            "lessons_updated": updated_count,
            "skyvern_status": skyvern_status,
            "extracted": extracted,
            "validation_details": details,
            "is_learning_check": is_learning_check,
            "tags": task.tags,
        }

    def run_round(
        self,
        tasks: list[BrowserTask],
        round_label: str,
    ) -> list[dict[str, Any]]:
        """Run all tasks in a single round."""
        print(f"\n{'#' * 60}")
        print(f"  {round_label}")
        print(f"{'#' * 60}")

        results: list[dict[str, Any]] = []
        for i, task in enumerate(tasks, 1):
            result = self.run_task(task, i, len(tasks))
            results.append(result)
            if i < len(tasks):
                wait = self.config.task_delay_seconds
                print(f"\n  Waiting {wait}s for lesson extraction...")
                time.sleep(wait)
        return results

    def run_multi_round(
        self,
        tasks: list[BrowserTask],
        rounds: int = 3,
    ) -> list[list[dict[str, Any]]]:
        """Run N rounds of all tasks, returning per-round results."""
        all_rounds: list[list[dict[str, Any]]] = []
        for r in range(1, rounds + 1):
            results = self.run_round(tasks, f"ROUND {r}/{rounds}")
            all_rounds.append(results)

            if r < rounds:
                wait = self.config.round_delay_seconds
                print(f"\n  === Waiting {wait}s between rounds for lesson extraction ===")
                time.sleep(wait)

        print_multi_round_summary(all_rounds)
        return all_rounds

    def close(self) -> None:
        """Clean up resources."""
        self.engram.close()
        self._skyvern.close()


# ---------------------------------------------------------------------------
# Summary printing
# ---------------------------------------------------------------------------


def print_round_summary(results: list[dict[str, Any]], round_label: str = "") -> None:
    """Print summary for a single round."""
    outcomes = {"success": 0, "partial": 0, "failure": 0}
    total_score = 0.0

    for r in results:
        outcomes[r.get("outcome", "failure")] = outcomes.get(r.get("outcome", "failure"), 0) + 1
        total_score += r.get("score", 0.0)

    n = len(results)
    prefix = f"  {round_label} " if round_label else "  "
    print(f"{prefix}Tasks: {n}  |  "
          f"Success: {outcomes['success']}  Partial: {outcomes['partial']}  Failure: {outcomes['failure']}  |  "
          f"Avg Score: {total_score / n:.2f}")


def print_multi_round_summary(all_rounds: list[list[dict[str, Any]]]) -> None:
    """Print comparison across multiple rounds."""
    print("\n" + "=" * 60)
    print("  MULTI-ROUND SUMMARY")
    print("=" * 60)

    for i, results in enumerate(all_rounds, 1):
        print_round_summary(results, f"Round {i}:")

    # Score progression per task
    if len(all_rounds) > 1:
        print(f"\n  Score Progression by Task:")
        print(f"  {'Task':<40}", end="")
        for i in range(len(all_rounds)):
            print(f"  R{i+1:>2}", end="")
        print(f"  {'Delta':>6}")
        print(f"  {'-' * 40}", end="")
        for _ in all_rounds:
            print(f"  {'---':>4}", end="")
        print(f"  {'------':>6}")

        tasks = all_rounds[0]
        for t_idx, task_result in enumerate(tasks):
            title = task_result["task"][:38]
            check = " *" if task_result.get("is_learning_check") else ""
            print(f"  {title + check:<40}", end="")
            scores = []
            for round_results in all_rounds:
                if t_idx < len(round_results):
                    s = round_results[t_idx].get("score", 0.0)
                    scores.append(s)
                    print(f"  {s:>4.2f}", end="")
                else:
                    print(f"  {'--':>4}", end="")
            delta = scores[-1] - scores[0] if len(scores) >= 2 else 0.0
            arrow = "+" if delta > 0 else "" if delta == 0 else ""
            print(f"  {arrow}{delta:>+5.2f}")

    # Learning pair analysis
    if len(all_rounds) >= 1:
        print(f"\n  LEARNING PAIR ANALYSIS (latest round)")
        print(f"  {'-' * 50}")
        latest = all_rounds[-1]

        for first, second, pattern in LEARNING_PAIRS:
            if first < len(latest) and second < len(latest):
                s1 = latest[first].get("score", 0.0)
                s2 = latest[second].get("score", 0.0)
                delta = s2 - s1
                arrow = "UP" if delta > 0 else "DOWN" if delta < 0 else "SAME"
                print(f"\n  {pattern}:")
                print(f"    {latest[first]['task'][:40]}: {s1:.2f}")
                print(f"    {latest[second]['task'][:40]}: {s2:.2f}")
                print(f"    Delta: {delta:+.2f} ({arrow})")

    # Overall improvement
    if len(all_rounds) >= 2:
        first_avg = sum(r.get("score", 0.0) for r in all_rounds[0]) / len(all_rounds[0])
        last_avg = sum(r.get("score", 0.0) for r in all_rounds[-1]) / len(all_rounds[-1])
        improvement = last_avg - first_avg

        print(f"\n  OVERALL:")
        print(f"    Round 1 avg: {first_avg:.2f}")
        print(f"    Round {len(all_rounds)} avg: {last_avg:.2f}")
        print(f"    Improvement: {improvement:+.2f}")

        if improvement > 0.05:
            print(f"\n  ** LEARNING DETECTED: Score improved by {improvement:+.2f} across rounds!")
        elif improvement > 0:
            print(f"\n  ~ Marginal improvement. More rounds or seed lessons may help.")
        else:
            print(f"\n  No improvement across rounds. Check lesson extraction pipeline.")

    print("\n  Check the Engram dashboard for traces and extracted lessons.")
    print("=" * 60)
