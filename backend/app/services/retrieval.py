import logging
from enum import Enum

from sqlalchemy import and_, func, literal_column, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import Lesson
from app.services.embedding import generate_embedding

logger = logging.getLogger(__name__)


class SearchMode(str, Enum):
    """Search mode for lesson retrieval."""

    VECTOR = "vector"
    KEYWORD = "keyword"
    HYBRID = "hybrid"


async def retrieve_similar_lessons(
    session: AsyncSession,
    query: str,
    agent_id: str | None = None,
    domain: str | None = None,
    top_k: int | None = None,
    min_confidence: float | None = None,
    search_mode: SearchMode = SearchMode.HYBRID,
    vector_weight: float = 0.7,
    include_archived: bool = False,
    utility_weight: float = 0.3,
) -> list[dict]:
    """
    Retrieve lessons similar to the query using configurable search modes.

    Two-phase retrieval:
      Phase A: hybrid/vector/keyword search fetching top_k * 3 candidates
      Phase B: re-rank by final_score = (1-utility_weight)*similarity*confidence + utility_weight*utility

    Args:
        session: Database session
        query: The search query
        agent_id: Optional filter by agent ID
        domain: Optional filter by domain
        top_k: Maximum number of results
        min_confidence: Minimum confidence threshold
        search_mode: "vector", "keyword", or "hybrid" (default)
        vector_weight: Weight for vector score in hybrid mode (0-1, default 0.7)
        include_archived: Include archived lessons (default False)
        utility_weight: Weight for utility in final re-ranking (0-1, default 0.3)

    Returns:
        List of lessons with similarity scores
    """
    top_k = top_k or settings.max_lessons_per_retrieval
    min_confidence = min_confidence or settings.min_confidence_threshold
    keyword_weight = 1.0 - vector_weight

    # Build base filters
    filters = [Lesson.confidence >= min_confidence]
    if not include_archived:
        filters.append(Lesson.is_archived == False)
    if agent_id:
        filters.append(Lesson.agent_id == agent_id)
    if domain:
        filters.append(Lesson.domain == domain)

    # Phase A: fetch candidates (top_k * 3 for re-ranking)
    candidate_k = top_k * 3

    if search_mode == SearchMode.VECTOR:
        candidates = await _vector_search(session, query, filters, candidate_k)
    elif search_mode == SearchMode.KEYWORD:
        candidates = await _keyword_search(session, query, filters, candidate_k)
    else:  # HYBRID
        candidates = await _hybrid_search(session, query, filters, candidate_k, vector_weight, keyword_weight)

    if not candidates:
        return []

    # Phase B: re-rank by utility-weighted final score
    if utility_weight > 0:
        for lesson in candidates:
            sim = lesson.get("similarity", 0.0)
            conf = lesson.get("confidence", 1.0)
            util = lesson.get("utility", 0.5)
            lesson["final_score"] = (1.0 - utility_weight) * sim * conf + utility_weight * util
        candidates.sort(key=lambda x: x["final_score"], reverse=True)
    else:
        for lesson in candidates:
            lesson["final_score"] = lesson.get("similarity", 0.0)

    return candidates[:top_k]


async def _vector_search(
    session: AsyncSession,
    query: str,
    filters: list,
    top_k: int,
) -> list[dict]:
    """Perform vector similarity search using pgvector."""
    query_embedding = generate_embedding(query)

    filters = list(filters)
    filters.append(Lesson.embedding.isnot(None))

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
            Lesson.has_conflict,
            Lesson.conflict_ids,
            Lesson.utility,
            similarity,
            literal_column("0.0").label("keyword_score"),
        )
        .where(and_(*filters))
        .order_by(Lesson.embedding.cosine_distance(query_embedding))
        .limit(top_k)
    )

    result = await session.execute(stmt)
    return _rows_to_lessons(result.fetchall())


async def _keyword_search(
    session: AsyncSession,
    query: str,
    filters: list,
    top_k: int,
) -> list[dict]:
    """Perform full-text search using PostgreSQL tsvector."""
    filters = list(filters)
    filters.append(Lesson.search_vector.isnot(None))

    ts_query = func.plainto_tsquery('english', query)
    keyword_score = func.ts_rank(Lesson.search_vector, ts_query).label("keyword_score")

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
            Lesson.has_conflict,
            Lesson.conflict_ids,
            Lesson.utility,
            literal_column("0.0").label("similarity"),
            keyword_score,
        )
        .where(and_(*filters, Lesson.search_vector.op('@@')(ts_query)))
        .order_by(keyword_score.desc())
        .limit(top_k)
    )

    result = await session.execute(stmt)
    rows = result.fetchall()

    lessons = _rows_to_lessons(rows)
    if lessons:
        max_score = max(l.get("keyword_score", 0) for l in lessons) or 1.0
        for lesson in lessons:
            lesson["keyword_score"] = lesson.get("keyword_score", 0) / max_score
            lesson["similarity"] = lesson["keyword_score"]

    return lessons


async def _hybrid_search(
    session: AsyncSession,
    query: str,
    filters: list,
    top_k: int,
    vector_weight: float,
    keyword_weight: float,
) -> list[dict]:
    """Perform hybrid search combining vector similarity and keyword search."""
    query_embedding = generate_embedding(query)
    ts_query = func.plainto_tsquery('english', query)

    vector_score = (1 - Lesson.embedding.cosine_distance(query_embedding)).label("vector_score")
    keyword_score = func.coalesce(
        func.ts_rank(Lesson.search_vector, ts_query),
        literal_column("0.0")
    ).label("keyword_score")

    filters = list(filters)
    filters.append(Lesson.embedding.isnot(None))

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
            Lesson.has_conflict,
            Lesson.conflict_ids,
            Lesson.utility,
            vector_score,
            keyword_score,
        )
        .where(and_(*filters))
        .limit(top_k)
    )

    result = await session.execute(stmt)
    rows = result.fetchall()

    if not rows:
        return []

    lessons = []
    max_keyword_score = max(row.keyword_score for row in rows) or 1.0

    for row in rows:
        normalized_keyword = row.keyword_score / max_keyword_score if max_keyword_score > 0 else 0
        vector_sim = float(row.vector_score) if row.vector_score else 0
        combined_score = (vector_weight * vector_sim) + (keyword_weight * normalized_keyword)

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
            "has_conflict": row.has_conflict,
            "conflict_ids": [str(cid) for cid in row.conflict_ids] if row.conflict_ids else [],
            "utility": float(row.utility) if row.utility is not None else 0.5,
            "similarity": combined_score,
            "vector_score": vector_sim,
            "keyword_score": normalized_keyword,
        })

    lessons.sort(key=lambda x: x["similarity"], reverse=True)
    return lessons


def _rows_to_lessons(rows) -> list[dict]:
    """Convert database rows to lesson dictionaries."""
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
            "has_conflict": row.has_conflict,
            "conflict_ids": [str(cid) for cid in row.conflict_ids] if row.conflict_ids else [],
            "utility": float(row.utility) if row.utility is not None else 0.5,
            "similarity": float(row.similarity) if row.similarity else 0.0,
            "keyword_score": float(row.keyword_score) if row.keyword_score else 0.0,
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
        conflict_warning = " ⚠️ CONFLICT" if lesson.get("has_conflict") else ""
        context_parts.append(
            f"### Lesson {i} [{outcome_emoji} {lesson['outcome']}] "
            f"(confidence: {lesson['confidence']:.2f}, utility: {lesson.get('utility', 0.5):.2f})"
            f"{conflict_warning}\n"
            f"**Context:** {lesson['task_context']}\n"
            f"**Action:** {lesson['action_taken']}\n"
            f"**Takeaway:** {lesson['lesson_text']}\n"
            f"**Tags:** {', '.join(lesson['tags'])}\n"
        )

    return "\n".join(context_parts)
