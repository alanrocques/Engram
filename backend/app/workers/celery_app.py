from celery import Celery
from celery.schedules import crontab

from app.config import settings

celery_app = Celery(
    "engram",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,  # 5 minutes max per task
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    # Celery Beat schedule for periodic tasks
    beat_schedule={
        "decay-lesson-confidence-daily": {
            "task": "app.workers.tasks.decay_confidence_task",
            "schedule": crontab(hour=2, minute=0),  # Run daily at 2 AM UTC
        },
        "process-pending-traces": {
            "task": "app.workers.tasks.process_pending_traces",
            "schedule": crontab(minute="*/5"),  # Run every 5 minutes
        },
        "batch-analyze-failures-weekly": {
            "task": "app.workers.tasks.batch_analyze_failures_task",
            "schedule": crontab(hour=3, minute=0, day_of_week=0),  # Sunday 3am UTC
        },
        "check-failure-queue-threshold": {
            "task": "app.workers.tasks.check_queue_threshold_task",
            "schedule": crontab(minute=0, hour="*/6"),  # Every 6 hours
        },
        "cleanup-toxic-lessons-weekly": {
            "task": "app.workers.tasks.cleanup_toxic_lessons_task",
            "schedule": crontab(hour=4, minute=0, day_of_week=6),  # Saturday 4am UTC
        },
    },
)
