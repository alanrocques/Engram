import logging
from datetime import datetime, timezone

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, update

from app.api.deps import AsyncSessionDep
from app.db.models import FailureQueue

router = APIRouter(prefix="/failure-queue", tags=["failure-queue"])
logger = logging.getLogger(__name__)


@router.get("/stats")
async def get_failure_queue_stats(session: AsyncSessionDep) -> dict:
    """Return counts of unprocessed failure queue entries by category and signature."""
    base_filter = FailureQueue.processed_at.is_(None)

    total_result = await session.execute(
        select(func.count(FailureQueue.id)).where(base_filter)
    )
    pending = total_result.scalar() or 0

    cat_result = await session.execute(
        select(FailureQueue.error_category, func.count(FailureQueue.id))
        .where(base_filter)
        .group_by(FailureQueue.error_category)
    )
    by_category = {row[0] or "unknown": row[1] for row in cat_result.all()}

    sig_result = await session.execute(
        select(FailureQueue.error_signature, func.count(FailureQueue.id))
        .where(base_filter)
        .group_by(FailureQueue.error_signature)
    )
    by_signature = {row[0] or "unknown": row[1] for row in sig_result.all()}

    return {"pending": pending, "by_category": by_category, "by_signature": by_signature}


@router.post("/analyze")
async def trigger_batch_analysis(session: AsyncSessionDep) -> JSONResponse:
    """Manually trigger batch failure analysis task.

    Tries Celery first (returns 202). If Celery is unavailable, runs
    the analysis inline and returns 200 with actual results.
    """
    try:
        from app.workers.tasks import batch_analyze_failures_task
        batch_analyze_failures_task.delay()
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={"status": "queued", "message": "Batch failure analysis queued"},
        )
    except Exception as e:
        logger.warning(f"Celery unavailable ({e}), running batch analysis inline")

    # Inline fallback: mirror logic from tasks.batch_analyze_failures_task
    from app.services.extraction import batch_analyze_failure_group

    result = await session.execute(
        select(FailureQueue.error_signature, func.count(FailureQueue.id).label("cnt"))
        .where(FailureQueue.processed_at.is_(None))
        .where(FailureQueue.error_signature.is_not(None))
        .group_by(FailureQueue.error_signature)
        .having(func.count(FailureQueue.id) >= 3)
    )
    groups = result.all()

    lessons_created = 0
    for row in groups:
        sig = row[0]
        ids_result = await session.execute(
            select(FailureQueue.id, FailureQueue.trace_id)
            .where(FailureQueue.processed_at.is_(None))
            .where(FailureQueue.error_signature == sig)
        )
        queue_rows = ids_result.all()
        trace_ids = [r[1] for r in queue_rows]
        queue_ids = [r[0] for r in queue_rows]

        lesson = await batch_analyze_failure_group(session, sig, trace_ids)
        if lesson:
            lessons_created += 1
            await session.execute(
                update(FailureQueue)
                .where(FailureQueue.id.in_(queue_ids))
                .values(processed_at=datetime.now(timezone.utc))
            )

    await session.commit()

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "status": "completed",
            "message": f"Analyzed {len(groups)} groups, created {lessons_created} lessons",
            "groups_processed": len(groups),
            "lessons_created": lessons_created,
        },
    )
