from fastapi import APIRouter

from app.api.deps import AsyncSessionDep
from app.schemas.retrieve import RetrieveRequest, RetrieveResponse, RetrievedLesson, SearchMode
from app.services.retrieval import (
    SearchMode as ServiceSearchMode,
    format_lessons_as_context,
    retrieve_similar_lessons,
)

router = APIRouter(prefix="/retrieve", tags=["retrieval"])


@router.post("", response_model=RetrieveResponse)
async def retrieve_lessons(
    request: RetrieveRequest,
    session: AsyncSessionDep,
) -> RetrieveResponse:
    """
    Retrieve lessons relevant to a given query.

    Supports three search modes:
    - **vector**: Semantic similarity search using embeddings
    - **keyword**: Full-text search using PostgreSQL tsvector
    - **hybrid** (default): Combines both with configurable weights

    Returns lessons sorted by similarity, optionally with a formatted context string
    that can be injected into an agent's prompt.
    """
    # Map schema enum to service enum
    search_mode_map = {
        SearchMode.VECTOR: ServiceSearchMode.VECTOR,
        SearchMode.KEYWORD: ServiceSearchMode.KEYWORD,
        SearchMode.HYBRID: ServiceSearchMode.HYBRID,
    }

    lessons = await retrieve_similar_lessons(
        session=session,
        query=request.query,
        agent_id=request.agent_id,
        domain=request.domain,
        top_k=request.top_k,
        min_confidence=request.min_confidence,
        search_mode=search_mode_map[request.search_mode],
        vector_weight=request.vector_weight,
        include_archived=request.include_archived,
        utility_weight=request.utility_weight,
    )

    context = None
    if request.include_context:
        context = format_lessons_as_context(lessons)

    return RetrieveResponse(
        lessons=[RetrievedLesson(**lesson) for lesson in lessons],
        context=context,
        total=len(lessons),
        search_mode=request.search_mode,
    )
