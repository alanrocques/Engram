import json
import logging
from typing import Any

import anthropic

from app.config import settings
from app.schemas.lesson import LessonCreate, OutcomeType

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """You are an expert at analyzing AI agent execution traces and extracting reusable lessons.

Given this agent execution trace:
<trace>
{trace_json}
</trace>

Extract a lesson from this trace. Analyze what the agent was trying to do, what actions it took, and whether it succeeded or failed.

Respond with a JSON object containing:
- task_context: A clear description of what the agent was trying to accomplish (1-2 sentences)
- action_taken: The specific action or approach the agent used (1-2 sentences)
- outcome: One of "success", "failure", or "partial"
- lesson_text: A concise, reusable takeaway that other agents can learn from (1-3 sentences). Focus on what worked, what didn't, or what to do differently.
- tags: An array of relevant category tags (e.g., ["error-handling", "api-calls", "retry-logic"])
- domain: A single category for this type of task (e.g., "web-browsing", "code-gen", "support", "data-processing")

Respond ONLY with the JSON object, no other text."""


def get_anthropic_client() -> anthropic.Anthropic:
    """Get Anthropic client."""
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


async def extract_lesson_from_trace(
    trace_data: dict[str, Any],
    agent_id: str,
    trace_id: str | None = None,
) -> LessonCreate | None:
    """Extract a lesson from an agent execution trace using Claude."""
    if not settings.anthropic_api_key:
        logger.warning("ANTHROPIC_API_KEY not set, skipping lesson extraction")
        return None

    try:
        client = get_anthropic_client()
        trace_json = json.dumps(trace_data, indent=2, default=str)

        message = client.messages.create(
            model=settings.extraction_model,
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": EXTRACTION_PROMPT.format(trace_json=trace_json),
                }
            ],
        )

        response_text = message.content[0].text
        lesson_data = json.loads(response_text)

        # Map outcome string to enum
        outcome_map = {
            "success": OutcomeType.SUCCESS,
            "failure": OutcomeType.FAILURE,
            "partial": OutcomeType.PARTIAL,
        }
        outcome = outcome_map.get(lesson_data.get("outcome", "").lower(), OutcomeType.PARTIAL)

        return LessonCreate(
            agent_id=agent_id,
            task_context=lesson_data.get("task_context", ""),
            state_snapshot={"trace_summary": trace_data.get("summary", {})},
            action_taken=lesson_data.get("action_taken", ""),
            outcome=outcome,
            lesson_text=lesson_data.get("lesson_text", ""),
            tags=lesson_data.get("tags", []),
            source_trace_id=trace_id,
            domain=lesson_data.get("domain", "general"),
        )

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Claude response as JSON: {e}")
        return None
    except anthropic.APIError as e:
        logger.error(f"Anthropic API error: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error during lesson extraction: {e}")
        return None
