import asyncio
import logging
from uuid import UUID

from app.db.engine import async_session_factory
from app.services.ingestion import generate_lesson_embedding, process_trace
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def run_async(coro):
    """Helper to run async code in sync Celery tasks."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(bind=True, max_retries=3)
def process_trace_task(self, trace_id: str):
    """
    Celery task to process a trace and extract a lesson.

    This task:
    1. Loads the trace from the database
    2. Calls Claude to extract a lesson
    3. Generates an embedding for the lesson
    4. Saves the lesson and updates the trace status
    """
    logger.info(f"Processing trace {trace_id}")

    async def _process():
        async with async_session_factory() as session:
            try:
                lesson = await process_trace(session, UUID(trace_id))
                await session.commit()
                return str(lesson.id) if lesson else None
            except Exception as e:
                await session.rollback()
                raise e

    try:
        result = run_async(_process())
        logger.info(f"Trace {trace_id} processed successfully, lesson: {result}")
        return {"status": "success", "trace_id": trace_id, "lesson_id": result}
    except Exception as e:
        logger.error(f"Failed to process trace {trace_id}: {e}")
        raise self.retry(exc=e, countdown=60)


@celery_app.task(bind=True, max_retries=3)
def generate_embedding_task(self, lesson_id: str):
    """
    Celery task to generate or regenerate embedding for a lesson.
    """
    logger.info(f"Generating embedding for lesson {lesson_id}")

    async def _generate():
        async with async_session_factory() as session:
            try:
                success = await generate_lesson_embedding(session, UUID(lesson_id))
                await session.commit()
                return success
            except Exception as e:
                await session.rollback()
                raise e

    try:
        result = run_async(_generate())
        return {"status": "success" if result else "failed", "lesson_id": lesson_id}
    except Exception as e:
        logger.error(f"Failed to generate embedding for lesson {lesson_id}: {e}")
        raise self.retry(exc=e, countdown=30)


@celery_app.task
def process_pending_traces():
    """
    Periodic task to process all pending traces.

    Can be scheduled with Celery Beat to run every few minutes.
    """
    from sqlalchemy import select

    from app.db.models import Trace

    logger.info("Processing pending traces")

    async def _get_pending():
        async with async_session_factory() as session:
            result = await session.execute(
                select(Trace.id).where(Trace.status == "pending").limit(100)
            )
            return [str(row[0]) for row in result.fetchall()]

    pending_ids = run_async(_get_pending())
    logger.info(f"Found {len(pending_ids)} pending traces")

    for trace_id in pending_ids:
        process_trace_task.delay(trace_id)

    return {"queued": len(pending_ids)}
