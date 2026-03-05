import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import AsyncSessionDep
from app.db.models import Trace
from app.schemas.trace import TraceCreate, TraceResponse, TraceStatus

router = APIRouter(prefix="/traces", tags=["traces"])
logger = logging.getLogger(__name__)


@router.post("", response_model=TraceResponse, status_code=status.HTTP_201_CREATED)
async def create_trace(
    trace_in: TraceCreate,
    session: AsyncSessionDep,
    process_async: bool = Query(default=True, description="Queue trace for async processing"),
) -> Trace:
    """
    Ingest a new agent execution trace.

    If process_async=True (default), the trace will be queued for background
    processing to extract lessons via Celery workers.
    """
    trace = Trace(
        agent_id=trace_in.agent_id,
        trace_data=trace_in.trace_data,
        span_count=trace_in.span_count,
        status="pending",
    )
    session.add(trace)
    try:
        await session.flush()
        await session.refresh(trace)
    except IntegrityError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create trace: {e}",
        )

    # Queue for async processing if requested
    if process_async:
        try:
            from app.workers.tasks import process_trace_task
            process_trace_task.delay(str(trace.id))
            logger.info(f"Queued trace {trace.id} for processing")
        except Exception as e:
            logger.warning(f"Failed to queue trace for processing: {e}")

    return trace


@router.post("/{trace_id}/process", status_code=status.HTTP_202_ACCEPTED)
async def process_trace_endpoint(trace_id: UUID, session: AsyncSessionDep) -> dict:
    """Manually trigger processing of a trace."""
    result = await session.execute(select(Trace).where(Trace.id == trace_id))
    trace = result.scalar_one_or_none()
    if not trace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trace {trace_id} not found",
        )

    try:
        from app.workers.tasks import process_trace_task
        process_trace_task.delay(str(trace_id))
        return {"status": "queued", "trace_id": str(trace_id)}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to queue trace for processing: {e}",
        )


@router.get("/{trace_id}", response_model=TraceResponse)
async def get_trace(trace_id: UUID, session: AsyncSessionDep) -> Trace:
    """Get a trace by ID."""
    result = await session.execute(select(Trace).where(Trace.id == trace_id))
    trace = result.scalar_one_or_none()
    if not trace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trace {trace_id} not found",
        )
    return trace


@router.get("", response_model=list[TraceResponse])
async def list_traces(
    session: AsyncSessionDep,
    agent_id: str | None = None,
    status: TraceStatus | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Trace]:
    """List traces with optional filtering."""
    query = select(Trace).order_by(Trace.created_at.desc()).offset(offset).limit(limit)

    if agent_id:
        query = query.where(Trace.agent_id == agent_id)
    if status:
        query = query.where(Trace.status == status.value)

    result = await session.execute(query)
    return list(result.scalars().all())
