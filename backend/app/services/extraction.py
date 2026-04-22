"""Lesson extraction service — routes traces by outcome to specialized extraction paths."""

import json
import logging
from typing import Any
from uuid import UUID

import anthropic
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import FailureQueue, Lesson, Trace
from app.services.embedding import generate_embedding

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LLM Prompts (concise, structured JSON output)
# ---------------------------------------------------------------------------

SUCCESS_PROMPT = """You are analyzing a successful AI agent execution trace to extract a reusable lesson.

Trace:
<trace>
{trace_json}
</trace>

Extract a success pattern lesson. Focus on: what worked, preconditions required, the reusable pattern, and when to apply it.

Respond ONLY with JSON:
{{
  "task_context": "what the agent was trying to do (1-2 sentences)",
  "action_taken": "the specific successful approach (1-2 sentences)",
  "lesson_text": "reusable takeaway with preconditions and when to apply (2-3 sentences)",
  "tags": ["tag1", "tag2"],
  "domain": "single domain category"
}}"""

PARTIAL_PROMPT = """You are analyzing a partially successful AI agent execution trace to extract a lesson.

Trace:
<trace>
{trace_json}
</trace>

Extract a comparative insight. Focus on: what almost worked, exactly where it broke down, and a hypothesis for how to fix it.

Respond ONLY with JSON:
{{
  "task_context": "what the agent was trying to do (1-2 sentences)",
  "action_taken": "the approach that partially worked (1-2 sentences)",
  "lesson_text": "what almost worked, where it broke, and fix hypothesis (2-3 sentences)",
  "tags": ["tag1", "tag2"],
  "domain": "single domain category"
}}"""

FAILURE_CLASSIFY_PROMPT = """Classify this failed AI agent execution trace to help group similar failures.

Trace:
<trace>
{trace_json}
</trace>

Respond ONLY with JSON:
{{
  "error_category": "high-level category (e.g. api_error, timeout, parsing_failure, auth_error, resource_not_found)",
  "error_signature": "short deterministic string identifying the failure pattern, max 80 chars (e.g. 'openai_rate_limit_on_completion', 'db_connection_timeout_retry_exhausted')"
}}"""

FAILURE_LESSON_PROMPT = """You are analyzing a failed AI agent execution trace to extract a specific, actionable lesson.

Trace:
<trace>
{trace_json}
</trace>

Extract a failure lesson. Focus on: the SPECIFIC action that failed, WHY it failed, and a CONCRETE alternative action the agent should take instead. Do NOT give generic advice like "add error handling" — be specific to this exact failure.

Respond ONLY with JSON:
{{
  "task_context": "what the agent was trying to do (1-2 sentences)",
  "action_taken": "the specific action that failed and why (1-2 sentences)",
  "lesson_text": "DO NOT: [specific bad action]. INSTEAD: [specific alternative]. REASON: [why the alternative works] (2-3 sentences)",
  "tags": ["tag1", "tag2"],
  "domain": "single domain category"
}}"""

BATCH_FAILURE_PROMPT = """You are analyzing {count} similar AI agent failures to extract a root cause lesson.

Failures (same error signature: {error_signature}):
<traces>
{traces_json}
</traces>

Extract a root cause analysis lesson. Focus on: the common root cause, how to prevent it, and how to detect it early.

Respond ONLY with JSON:
{{
  "task_context": "common task context across these failures (1-2 sentences)",
  "action_taken": "the common failing approach (1-2 sentences)",
  "lesson_text": "root cause, prevention strategy, and early detection pattern (3-4 sentences)",
  "tags": ["tag1", "tag2"],
  "domain": "single domain category"
}}"""

GENERIC_PROMPT = """You are an expert at analyzing AI agent execution traces and extracting reusable lessons.

Given this agent execution trace:
<trace>
{trace_json}
</trace>

Extract a lesson. Analyze what the agent was trying to do, what actions it took, and whether it succeeded or failed.

Respond ONLY with JSON:
{{
  "task_context": "what the agent was trying to accomplish (1-2 sentences)",
  "action_taken": "the specific action or approach used (1-2 sentences)",
  "outcome": "success, failure, or partial",
  "lesson_text": "concise reusable takeaway (1-3 sentences)",
  "tags": ["tag1", "tag2"],
  "domain": "single domain category"
}}"""


def get_anthropic_client() -> anthropic.Anthropic:
    """Get Anthropic client."""
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


def _call_claude(prompt: str) -> dict[str, Any] | None:
    """Call Claude and parse JSON response. Returns None on any error."""
    if not settings.anthropic_api_key:
        logger.warning("ANTHROPIC_API_KEY not set, skipping LLM extraction")
        return None
    try:
        client = get_anthropic_client()
        message = client.messages.create(
            model=settings.extraction_model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        text = message.content[0].text.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first line (```json) and last line (```)
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines).strip()
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Claude response as JSON: {e}")
        return None
    except anthropic.APIError as e:
        logger.error(f"Anthropic API error: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error during LLM call: {e}")
        return None


def _build_lesson(
    trace: Trace,
    data: dict[str, Any],
    outcome: str,
    lesson_type: str,
    initial_utility: float,
    extraction_mode: str = "immediate",
    source_trace_ids: list[UUID] | None = None,
) -> Lesson:
    """Construct a Lesson ORM object from extracted data."""
    embedding_text = f"{data.get('task_context', '')} {data.get('action_taken', '')} {data.get('lesson_text', '')}"
    embedding = generate_embedding(embedding_text)

    return Lesson(
        agent_id=trace.agent_id,
        task_context=data.get("task_context", ""),
        state_snapshot={},
        action_taken=data.get("action_taken", ""),
        outcome=outcome,
        lesson_text=data.get("lesson_text", ""),
        embedding=embedding,
        tags=data.get("tags", []),
        domain=data.get("domain", "general"),
        lesson_type=lesson_type,
        extraction_mode=extraction_mode,
        utility=initial_utility,
        source_trace_ids=source_trace_ids,
    )


# ---------------------------------------------------------------------------
# Public routing entrypoint
# ---------------------------------------------------------------------------

async def route_trace_extraction(
    session: AsyncSession,
    trace_id: UUID,
    outcome: str,
) -> Lesson | None:
    """
    Route trace extraction based on outcome:
      success  → immediate success_pattern lesson (utility 0.6)
      failure  → classify + queue in failure_queue, no lesson yet
      partial  → immediate comparative_insight lesson (utility 0.5)
      unknown  → generic extraction (utility 0.5)
    """
    result = await session.execute(select(Trace).where(Trace.id == trace_id))
    trace = result.scalar_one_or_none()
    if not trace:
        logger.error(f"Trace {trace_id} not found for extraction")
        return None

    outcome_lower = outcome.lower()

    if outcome_lower == "success":
        return await _extract_success_pattern(trace, session)
    elif outcome_lower == "failure":
        await _queue_failure(trace, session)
        return await _extract_failure_lesson(trace, session)
    elif outcome_lower == "partial":
        return await _extract_partial_insight(trace, session)
    else:
        return await _generic_extract(trace, session)


async def _extract_success_pattern(trace: Trace, session: AsyncSession) -> Lesson | None:
    trace_json = json.dumps(trace.trace_data, indent=2, default=str)
    data = _call_claude(SUCCESS_PROMPT.format(trace_json=trace_json))
    if not data:
        return None

    lesson = _build_lesson(
        trace=trace,
        data=data,
        outcome="success",
        lesson_type="success_pattern",
        initial_utility=0.6,
        extraction_mode="immediate",
    )
    session.add(lesson)
    await session.flush()
    await session.refresh(lesson)
    logger.info(f"Extracted success_pattern lesson {lesson.id} from trace {trace.id}")
    return lesson


async def _extract_partial_insight(trace: Trace, session: AsyncSession) -> Lesson | None:
    trace_json = json.dumps(trace.trace_data, indent=2, default=str)
    data = _call_claude(PARTIAL_PROMPT.format(trace_json=trace_json))
    if not data:
        return None

    lesson = _build_lesson(
        trace=trace,
        data=data,
        outcome="partial",
        lesson_type="comparative_insight",
        initial_utility=0.5,
        extraction_mode="immediate",
    )
    session.add(lesson)
    await session.flush()
    await session.refresh(lesson)
    logger.info(f"Extracted comparative_insight lesson {lesson.id} from trace {trace.id}")
    return lesson


async def _extract_failure_lesson(trace: Trace, session: AsyncSession) -> Lesson | None:
    """Extract an immediate failure_pattern lesson from a failed trace."""
    trace_json = json.dumps(trace.trace_data, indent=2, default=str)
    data = _call_claude(FAILURE_LESSON_PROMPT.format(trace_json=trace_json))
    if not data:
        return None

    lesson = _build_lesson(
        trace=trace,
        data=data,
        outcome="failure",
        lesson_type="failure_pattern",
        initial_utility=0.4,
        extraction_mode="immediate",
    )
    session.add(lesson)
    await session.flush()
    await session.refresh(lesson)
    logger.info(f"Extracted failure_pattern lesson {lesson.id} from trace {trace.id}")
    return lesson


async def _queue_failure(trace: Trace, session: AsyncSession) -> None:
    """Classify failure and add to failure_queue. No lesson created yet."""
    trace_json = json.dumps(trace.trace_data, indent=2, default=str)
    data = _call_claude(FAILURE_CLASSIFY_PROMPT.format(trace_json=trace_json))

    error_category = data.get("error_category") if data else None
    error_signature = data.get("error_signature") if data else None

    queue_entry = FailureQueue(
        trace_id=trace.id,
        agent_id=trace.agent_id,
        error_category=error_category,
        error_signature=error_signature,
    )
    session.add(queue_entry)
    await session.flush()
    logger.info(
        f"Queued failure trace {trace.id} (category={error_category}, sig={error_signature})"
    )


async def _generic_extract(trace: Trace, session: AsyncSession) -> Lesson | None:
    """Fallback: existing generic extraction for 'unknown' outcome traces."""
    trace_json = json.dumps(trace.trace_data, indent=2, default=str)
    data = _call_claude(GENERIC_PROMPT.format(trace_json=trace_json))
    if not data:
        return None

    outcome_map = {"success": "success", "failure": "failure", "partial": "partial"}
    outcome = outcome_map.get(data.get("outcome", "").lower(), "partial")

    lesson = _build_lesson(
        trace=trace,
        data=data,
        outcome=outcome,
        lesson_type="general",
        initial_utility=0.5,
        extraction_mode="immediate",
    )
    session.add(lesson)
    await session.flush()
    await session.refresh(lesson)
    logger.info(f"Extracted general lesson {lesson.id} from trace {trace.id}")
    return lesson


# ---------------------------------------------------------------------------
# Batch failure analysis (called by Celery task)
# ---------------------------------------------------------------------------

async def batch_analyze_failure_group(
    session: AsyncSession,
    error_signature: str,
    trace_ids: list[UUID],
) -> Lesson | None:
    """
    Load up to 5 traces with the same error_signature and extract a root_cause lesson
    via comparative LLM analysis.
    """
    # Load traces (up to 5)
    sample_ids = trace_ids[:5]
    results = await session.execute(select(Trace).where(Trace.id.in_(sample_ids)))
    traces = results.scalars().all()

    if not traces:
        return None

    traces_json = json.dumps(
        [{"trace_id": str(t.id), "data": t.trace_data} for t in traces],
        indent=2,
        default=str,
    )

    data = _call_claude(
        BATCH_FAILURE_PROMPT.format(
            count=len(traces),
            error_signature=error_signature,
            traces_json=traces_json,
        )
    )
    if not data:
        return None

    # Use the first trace for agent_id / as representative
    representative = traces[0]
    embedding_text = f"{data.get('task_context', '')} {data.get('action_taken', '')} {data.get('lesson_text', '')}"
    embedding = generate_embedding(embedding_text)

    lesson = Lesson(
        agent_id=representative.agent_id,
        task_context=data.get("task_context", ""),
        state_snapshot={},
        action_taken=data.get("action_taken", ""),
        outcome="failure",
        lesson_text=data.get("lesson_text", ""),
        embedding=embedding,
        tags=data.get("tags", []),
        domain=data.get("domain", "general"),
        lesson_type="root_cause",
        extraction_mode="batch",
        utility=0.5,
        source_trace_ids=trace_ids,
    )
    session.add(lesson)
    await session.flush()
    await session.refresh(lesson)
    logger.info(
        f"Created root_cause lesson {lesson.id} from {len(trace_ids)} failures "
        f"(sig={error_signature})"
    )
    return lesson


# ---------------------------------------------------------------------------
# Legacy alias — kept for backward compatibility with existing process_trace call
# ---------------------------------------------------------------------------

async def extract_lesson_from_trace(
    trace_data: dict[str, Any],
    agent_id: str,
    trace_id: str | None = None,
) -> None:
    """Deprecated: use route_trace_extraction() instead."""
    logger.warning("extract_lesson_from_trace() is deprecated; use route_trace_extraction()")
    return None
