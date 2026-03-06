import logging

from fastapi import APIRouter

from app.api.deps import AsyncSessionDep
from app.schemas.outcome import OutcomeRequest, OutcomeResponse
from app.services import provenance as provenance_service
from app.services import utility as utility_service

router = APIRouter(prefix="/outcomes", tags=["outcomes"])
logger = logging.getLogger(__name__)


@router.post("", response_model=OutcomeResponse)
async def report_outcome(
    request: OutcomeRequest,
    session: AsyncSessionDep,
) -> OutcomeResponse:
    """
    Report the outcome of a trace and update utility scores and provenance.

    Orchestrates: (1) record trace context, (2) record retrievals, (3) update
    utility scores via Bellman EMA, (4) propagate failure penalties if applicable.
    """
    # 1. Record provenance context (which lessons were in context for this trace)
    if request.retrieved_lesson_ids:
        try:
            await provenance_service.record_trace_context(
                session=session,
                trace_id=request.trace_id,
                retrieved_lesson_ids=list(request.retrieved_lesson_ids),
            )
        except Exception as e:
            logger.warning(f"Failed to record trace context: {e}")

    # 2. Record retrievals for utility tracking
    if request.retrieved_lesson_ids:
        for lesson_id in request.retrieved_lesson_ids:
            try:
                await utility_service.record_retrieval(
                    session=session,
                    lesson_id=lesson_id,
                    trace_id=request.trace_id,
                    context_similarity=request.context_similarity,
                )
            except Exception as e:
                logger.warning(f"Failed to record retrieval for lesson {lesson_id}: {e}")

    # 3. Update utility scores via Bellman EMA
    updated_ids = await utility_service.report_outcome(
        session=session,
        trace_id=request.trace_id,
        outcome=request.outcome,
        downstream_utility=request.downstream_utility,
    )

    # 4. Propagate failure penalty through lesson lineage
    if request.outcome == "failure" and request.retrieved_lesson_ids:
        try:
            await provenance_service.propagate_failure_penalty(
                session=session,
                trace_id=request.trace_id,
            )
        except Exception as e:
            logger.warning(f"Failed to propagate failure penalty: {e}")

    return OutcomeResponse(
        trace_id=str(request.trace_id),
        outcome=request.outcome,
        updated_lesson_ids=[str(uid) for uid in updated_ids],
        updated_count=len(updated_ids),
    )
