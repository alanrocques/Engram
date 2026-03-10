import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import AsyncSessionDep
from app.db.models import Trace
from app.schemas.trace import TraceBatchCreate, TraceBatchResponse, TraceCreate, TraceDeleteBulk, TraceResponse, TraceStatus
from app.services.ingestion import compute_trace_hash, check_trace_duplicate, ingest_trace_batch

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

    Duplicate traces (same content hash) are rejected with 409. If
    process_async=True (default), the trace is queued for background lesson
    extraction via Celery workers.
    """
    content_hash = compute_trace_hash(trace_in.trace_data)

    if await check_trace_duplicate(session, content_hash):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Duplicate trace: identical content already processed",
        )

    trace = Trace(
        agent_id=trace_in.agent_id,
        trace_data=trace_in.trace_data,
        span_count=trace_in.span_count,
        status="pending",
        content_hash=content_hash,
        outcome=trace_in.outcome,
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


@router.post("/batch", response_model=TraceBatchResponse, status_code=status.HTTP_201_CREATED)
async def create_traces_batch(
    batch_in: TraceBatchCreate,
    session: AsyncSessionDep,
    process_async: bool = Query(default=True, description="Queue traces for async processing"),
) -> TraceBatchResponse:
    """
    Ingest a batch of agent execution traces (max 50).

    Duplicate traces are silently skipped. If process_async=True (default),
    all created traces are queued for background lesson extraction.
    """
    result = await ingest_trace_batch(session, batch_in.traces, batch_in.agent_id)

    if process_async and result["trace_ids"]:
        try:
            from app.workers.tasks import process_trace_task
            for trace_id in result["trace_ids"]:
                process_trace_task.delay(trace_id)
            logger.info(f"Queued {len(result['trace_ids'])} traces for processing")
        except Exception as e:
            logger.warning(f"Failed to queue batch traces for processing: {e}")

    return TraceBatchResponse(**result)


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


@router.delete("/{trace_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_trace(trace_id: UUID, session: AsyncSessionDep) -> None:
    """Delete a trace by ID. Cascades to related failure queue and lesson retrieval entries."""
    trace = await session.get(Trace, trace_id)
    if not trace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trace {trace_id} not found",
        )
    await session.delete(trace)
    await session.commit()


@router.post("/delete", status_code=status.HTTP_204_NO_CONTENT)
async def delete_traces_bulk(body: TraceDeleteBulk, session: AsyncSessionDep) -> None:
    """Bulk delete traces by IDs (max 100). Cascades to related entries."""
    await session.execute(delete(Trace).where(Trace.id.in_(body.ids)))
    await session.commit()


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
