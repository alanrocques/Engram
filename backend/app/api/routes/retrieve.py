from fastapi import APIRouter

from app.api.deps import AsyncSessionDep
from app.schemas.retrieve import RetrieveRequest, RetrieveResponse, RetrievedLesson
from app.services.retrieval import format_lessons_as_context, retrieve_similar_lessons

router = APIRouter(prefix="/retrieve", tags=["retrieval"])


@router.post("", response_model=RetrieveResponse)
async def retrieve_lessons(
    request: RetrieveRequest,
    session: AsyncSessionDep,
) -> RetrieveResponse:
    """
    Retrieve lessons relevant to a given query using vector similarity search.

    Returns lessons sorted by similarity, optionally with a formatted context string
    that can be injected into an agent's prompt.
    """
    lessons = await retrieve_similar_lessons(
        session=session,
        query=request.query,
        agent_id=request.agent_id,
        domain=request.domain,
        top_k=request.top_k,
        min_confidence=request.min_confidence,
    )

    context = None
    if request.include_context:
        context = format_lessons_as_context(lessons)

    return RetrieveResponse(
        lessons=[RetrievedLesson(**lesson) for lesson in lessons],
        context=context,
        total=len(lessons),
    )
