from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import AsyncSessionDep
from app.db.models import Lesson
from app.schemas.lesson import LessonCreate, LessonResponse, LessonUpdate

router = APIRouter(prefix="/lessons", tags=["lessons"])


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
    return lesson


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


@router.get("", response_model=list[LessonResponse])
async def list_lessons(
    session: AsyncSessionDep,
    agent_id: str | None = None,
    domain: str | None = None,
    outcome: str | None = None,
    min_confidence: float = 0.0,
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

    result = await session.execute(query)
    return list(result.scalars().all())


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
