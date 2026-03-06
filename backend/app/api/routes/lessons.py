import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import AsyncSessionDep
from app.db.models import Lesson
from app.schemas.lesson import ConflictListResponse, ConflictResponse, LessonCreate, LessonResponse, LessonUpdate
from app.services.curation import get_all_conflicts
from app.services.provenance import get_lesson_provenance

router = APIRouter(prefix="/lessons", tags=["lessons"])
logger = logging.getLogger(__name__)


@router.post("", response_model=LessonResponse, status_code=status.HTTP_201_CREATED)
async def create_lesson(lesson_in: LessonCreate, session: AsyncSessionDep) -> Lesson:
    """Create a new lesson manually."""
    lesson = Lesson(
        agent_id=lesson_in.agent_id,
        task_context=lesson_in.task_context,
        state_snapshot=lesson_in.state_snapshot,
        action_taken=lesson_in.action_taken,
        outcome=lesson_in.outcome.value,
        lesson_text=lesson_in.lesson_text,
        tags=lesson_in.tags,
        source_trace_id=lesson_in.source_trace_id,
        domain=lesson_in.domain,
    )
    session.add(lesson)
    try:
        await session.flush()
        await session.refresh(lesson)
    except IntegrityError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create lesson: {e}",
        )

    # Queue embedding generation and conflict detection as background tasks
    try:
        from app.workers.tasks import detect_conflicts_task, generate_embedding_task
        generate_embedding_task.delay(str(lesson.id))
        detect_conflicts_task.delay(str(lesson.id))
    except Exception as e:
        logger.warning(f"Failed to queue background tasks for lesson {lesson.id}: {e}")

    return lesson


@router.get("/conflicts", response_model=ConflictListResponse)
async def list_conflicts(session: AsyncSessionDep) -> ConflictListResponse:
    """
    List all lessons that have detected conflicts.

    Returns groups of lessons with contradictory outcomes on similar tasks,
    for human review and resolution.
    """
    conflicts = await get_all_conflicts(session)
    return ConflictListResponse(
        conflicts=[ConflictResponse(**c) for c in conflicts],
        total=len(conflicts),
    )


@router.get("/flagged", response_model=list[LessonResponse])
async def list_flagged_lessons(session: AsyncSessionDep) -> list[Lesson]:
    """List lessons flagged for review due to accumulated failure penalties."""
    result = await session.execute(
        select(Lesson)
        .where(Lesson.needs_review == True)  # noqa: E712
        .where(Lesson.is_archived == False)  # noqa: E712
        .order_by(Lesson.propagation_penalty.desc())
        .limit(100)
    )
    return list(result.scalars().all())


@router.get("", response_model=list[LessonResponse])
async def list_lessons(
    session: AsyncSessionDep,
    agent_id: str | None = None,
    domain: str | None = None,
    outcome: str | None = None,
    min_confidence: float = 0.0,
    include_archived: bool = False,
    limit: int = 100,
    offset: int = 0,
) -> list[Lesson]:
    """List lessons with optional filtering."""
    query = (
        select(Lesson)
        .where(Lesson.confidence >= min_confidence)
        .order_by(Lesson.created_at.desc())
        .offset(offset)
        .limit(limit)
    )

    if agent_id:
        query = query.where(Lesson.agent_id == agent_id)
    if domain:
        query = query.where(Lesson.domain == domain)
    if outcome:
        query = query.where(Lesson.outcome == outcome)
    if not include_archived:
        query = query.where(Lesson.is_archived == False)

    result = await session.execute(query)
    return list(result.scalars().all())


@router.get("/{lesson_id}", response_model=LessonResponse)
async def get_lesson(lesson_id: UUID, session: AsyncSessionDep) -> Lesson:
    """Get a lesson by ID."""
    result = await session.execute(select(Lesson).where(Lesson.id == lesson_id))
    lesson = result.scalar_one_or_none()
    if not lesson:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lesson {lesson_id} not found",
        )
    return lesson


@router.patch("/{lesson_id}", response_model=LessonResponse)
async def update_lesson(
    lesson_id: UUID,
    lesson_update: LessonUpdate,
    session: AsyncSessionDep,
) -> Lesson:
    """Update a lesson."""
    result = await session.execute(select(Lesson).where(Lesson.id == lesson_id))
    lesson = result.scalar_one_or_none()
    if not lesson:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lesson {lesson_id} not found",
        )

    update_data = lesson_update.model_dump(exclude_unset=True)
    if "outcome" in update_data and update_data["outcome"] is not None:
        update_data["outcome"] = update_data["outcome"].value

    for field, value in update_data.items():
        setattr(lesson, field, value)

    lesson.version += 1
    await session.flush()
    await session.refresh(lesson)
    return lesson


@router.delete("/{lesson_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_lesson(lesson_id: UUID, session: AsyncSessionDep) -> None:
    """Delete a lesson."""
    result = await session.execute(select(Lesson).where(Lesson.id == lesson_id))
    lesson = result.scalar_one_or_none()
    if not lesson:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lesson {lesson_id} not found",
        )
    await session.delete(lesson)


@router.get("/{lesson_id}/provenance")
async def get_provenance(lesson_id: UUID, session: AsyncSessionDep) -> dict:
    """Get the full provenance record for a lesson."""
    provenance = await get_lesson_provenance(session, lesson_id)
    if not provenance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lesson {lesson_id} not found",
        )
    return provenance


@router.post("/{lesson_id}/boost", response_model=LessonResponse)
async def boost_lesson_confidence(
    lesson_id: UUID,
    session: AsyncSessionDep,
    boost_amount: float = 0.1,
) -> Lesson:
    """
    Boost a lesson's confidence after successful use or human validation.

    The boost is applied asynchronously via a Celery task. The current lesson
    state is returned immediately.
    """
    result = await session.execute(select(Lesson).where(Lesson.id == lesson_id))
    lesson = result.scalar_one_or_none()
    if not lesson:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lesson {lesson_id} not found",
        )

    try:
        from app.workers.tasks import boost_confidence_task
        boost_confidence_task.delay(str(lesson_id), boost_amount)
    except Exception as e:
        logger.warning(f"Failed to queue confidence boost for lesson {lesson_id}: {e}")

    await session.refresh(lesson)
    return lesson
