import logging

from sqlalchemy import Float, and_, cast, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import Lesson
from app.services.embedding import generate_embedding

logger = logging.getLogger(__name__)


async def retrieve_similar_lessons(
    session: AsyncSession,
    query: str,
    agent_id: str | None = None,
    domain: str | None = None,
    top_k: int | None = None,
    min_confidence: float | None = None,
) -> list[dict]:
    """
    Retrieve lessons similar to the query using vector similarity search.

    Returns lessons with their similarity scores, formatted for use as agent context.
    """
    top_k = top_k or settings.max_lessons_per_retrieval
    min_confidence = min_confidence or settings.min_confidence_threshold

    # Generate embedding for the query
    query_embedding = generate_embedding(query)

    # Build filters
    filters = [
        Lesson.confidence >= min_confidence,
        Lesson.embedding.isnot(None),
    ]
    if agent_id:
        filters.append(Lesson.agent_id == agent_id)
    if domain:
        filters.append(Lesson.domain == domain)

    # Calculate similarity (1 - cosine_distance)
    # pgvector's <=> operator returns cosine distance
    similarity = (1 - Lesson.embedding.cosine_distance(query_embedding)).label("similarity")

    stmt = (
        select(
            Lesson.id,
            Lesson.agent_id,
            Lesson.task_context,
            Lesson.action_taken,
            Lesson.outcome,
            Lesson.lesson_text,
            Lesson.confidence,
            Lesson.tags,
            Lesson.domain,
            Lesson.created_at,
            similarity,
        )
        .where(and_(*filters))
        .order_by(Lesson.embedding.cosine_distance(query_embedding))
        .limit(top_k)
    )

    result = await session.execute(stmt)
    rows = result.fetchall()

    lessons = []
    for row in rows:
        lessons.append({
            "id": str(row.id),
            "agent_id": row.agent_id,
            "task_context": row.task_context,
            "action_taken": row.action_taken,
            "outcome": row.outcome,
            "lesson_text": row.lesson_text,
            "confidence": row.confidence,
            "tags": row.tags,
            "domain": row.domain,
            "similarity": float(row.similarity) if row.similarity else 0.0,
        })

    return lessons


def format_lessons_as_context(lessons: list[dict]) -> str:
    """Format retrieved lessons as context for an agent prompt."""
    if not lessons:
        return ""

    context_parts = ["## Relevant Lessons from Past Experience\n"]

    for i, lesson in enumerate(lessons, 1):
        outcome_emoji = {"success": "✓", "failure": "✗", "partial": "~"}.get(
            lesson["outcome"], "?"
        )
        context_parts.append(
            f"### Lesson {i} [{outcome_emoji} {lesson['outcome']}] (confidence: {lesson['confidence']:.2f})\n"
            f"**Context:** {lesson['task_context']}\n"
            f"**Action:** {lesson['action_taken']}\n"
            f"**Takeaway:** {lesson['lesson_text']}\n"
            f"**Tags:** {', '.join(lesson['tags'])}\n"
        )

    return "\n".join(context_parts)
