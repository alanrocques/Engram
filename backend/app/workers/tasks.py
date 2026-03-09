import asyncio
import logging
from uuid import UUID

from app.db.engine import async_session_factory
from app.services.ingestion import generate_lesson_embedding, process_trace
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def run_async(coro):
    """Helper to run async code in sync Celery tasks.

    Creates a fresh event loop and disposes the engine afterward
    to prevent connection pool leaks across loops.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        # Dispose the engine to prevent connections leaking across event loops
        from app.db.engine import engine
        loop.run_until_complete(engine.dispose())
        loop.close()


@celery_app.task(bind=True, max_retries=3, rate_limit='6/m')
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
        from sqlalchemy import select
        from app.db.models import Trace

        async with async_session_factory() as session:
            try:
                result = await session.execute(select(Trace.outcome).where(Trace.id == UUID(trace_id)))
                row = result.first()
                outcome = (row[0] if row and row[0] else "unknown")
                lesson = await process_trace(session, UUID(trace_id), outcome=outcome)
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


@celery_app.task
def decay_confidence_task():
    """
    Periodic task to decay lesson confidence based on age.

    Runs daily via Celery Beat. Applies exponential decay and archives
    lessons below the minimum confidence threshold.
    """
    from app.services.curation import decay_lesson_confidence

    logger.info("Running confidence decay task")

    async def _decay():
        async with async_session_factory() as session:
            return await decay_lesson_confidence(session)

    result = run_async(_decay())
    logger.info(f"Confidence decay complete: {result}")
    return result


@celery_app.task(bind=True, max_retries=3)
def detect_conflicts_task(self, lesson_id: str):
    """
    Celery task to detect conflicts for a newly created lesson.
    """
    from app.services.curation import detect_conflicts

    logger.info(f"Detecting conflicts for lesson {lesson_id}")

    async def _detect():
        async with async_session_factory() as session:
            try:
                conflicts = await detect_conflicts(session, UUID(lesson_id))
                return [str(cid) for cid in conflicts]
            except Exception as e:
                await session.rollback()
                raise e

    try:
        result = run_async(_detect())
        logger.info(f"Conflict detection complete for {lesson_id}: {len(result)} conflicts")
        return {"lesson_id": lesson_id, "conflicts": result}
    except Exception as e:
        logger.error(f"Failed to detect conflicts for {lesson_id}: {e}")
        raise self.retry(exc=e, countdown=30)


@celery_app.task
def batch_analyze_failures_task():
    """
    Periodic task to batch-analyze grouped failure traces.

    Groups failure_queue entries by error_signature. For groups with 3+
    entries, runs comparative LLM analysis and creates a root_cause lesson.
    """
    from datetime import datetime, timezone
    from sqlalchemy import select, func, update
    from app.db.models import FailureQueue
    from app.services.extraction import batch_analyze_failure_group

    logger.info("Running batch failure analysis")

    async def _analyze():
        async with async_session_factory() as session:
            # Group unprocessed entries by error_signature with count >= 3
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
                # Get trace_ids for this group
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
                    # Mark queue rows processed
                    await session.execute(
                        update(FailureQueue)
                        .where(FailureQueue.id.in_(queue_ids))
                        .values(processed_at=datetime.now(timezone.utc))
                    )

            await session.commit()
            return {"groups_processed": len(groups), "lessons_created": lessons_created}

    result = run_async(_analyze())
    logger.info(f"Batch failure analysis complete: {result}")
    return result


@celery_app.task
def check_queue_threshold_task(threshold: int = 20):
    """
    Check if failure_queue has exceeded the threshold, and if so trigger batch analysis.
    """
    from sqlalchemy import select, func
    from app.db.models import FailureQueue

    async def _check():
        async with async_session_factory() as session:
            result = await session.execute(
                select(func.count(FailureQueue.id)).where(FailureQueue.processed_at.is_(None))
            )
            count = result.scalar() or 0
            return count

    count = run_async(_check())
    logger.info(f"Failure queue has {count} unprocessed entries (threshold={threshold})")
    if count >= threshold:
        batch_analyze_failures_task.delay()
        return {"triggered": True, "count": count}
    return {"triggered": False, "count": count}


@celery_app.task
def cleanup_toxic_lessons_task():
    """
    Archive lessons with high propagation penalty and low utility.

    Targets lessons with propagation_penalty > 0.5, utility < 0.15,
    retrieval_count > 5, and not yet archived.
    """
    from datetime import datetime, timezone
    from sqlalchemy import select, update
    from app.db.models import Lesson, ProvenanceEvent

    logger.info("Running toxic lessons cleanup task")

    async def _cleanup():
        async with async_session_factory() as session:
            result = await session.execute(
                select(Lesson.id).where(
                    Lesson.propagation_penalty > 0.5,
                    Lesson.utility < 0.15,
                    Lesson.retrieval_count > 5,
                    Lesson.is_archived == False,  # noqa: E712
                )
            )
            ids = [row[0] for row in result.all()]
            if not ids:
                return {"archived": 0}

            await session.execute(
                update(Lesson).where(Lesson.id.in_(ids)).values(is_archived=True)
            )
            for lesson_id in ids:
                session.add(ProvenanceEvent(
                    event_type="auto_archived",
                    lesson_id=lesson_id,
                    payload={"reason": "toxic: high penalty + low utility"},
                ))
            await session.commit()
            return {"archived": len(ids)}

    result = run_async(_cleanup())
    logger.info(f"Toxic lessons cleanup: {result}")
    return result


@celery_app.task(bind=True, max_retries=3)
def boost_confidence_task(self, lesson_id: str, boost_amount: float = 0.1):
    """
    Celery task to boost a lesson's confidence after successful use.
    """
    from app.services.curation import boost_lesson_confidence

    logger.info(f"Boosting confidence for lesson {lesson_id}")

    async def _boost():
        async with async_session_factory() as session:
            return await boost_lesson_confidence(session, UUID(lesson_id), boost_amount)

    try:
        new_confidence = run_async(_boost())
        return {"lesson_id": lesson_id, "new_confidence": new_confidence}
    except Exception as e:
        logger.error(f"Failed to boost confidence for {lesson_id}: {e}")
        raise self.retry(exc=e, countdown=30)
