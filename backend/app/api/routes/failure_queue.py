import logging

from fastapi import APIRouter, status
from sqlalchemy import func, select

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


@router.post("/analyze", status_code=status.HTTP_202_ACCEPTED)
async def trigger_batch_analysis() -> dict:
    """Manually trigger batch failure analysis task."""
    try:
        from app.workers.tasks import batch_analyze_failures_task
        batch_analyze_failures_task.delay()
        return {"status": "queued", "message": "Batch failure analysis queued"}
    except Exception as e:
        logger.warning(f"Failed to queue batch analysis: {e}")
        return {"status": "queued", "message": "Batch failure analysis queued (Celery unavailable)"}
