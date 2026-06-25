import os

from celery import Celery
from celery.schedules import crontab

from mediaforge.config import get_settings


def create_celery() -> Celery:
    settings = get_settings()
    broker_url = os.getenv("CELERY_BROKER_URL", settings.redis_url)

    app = Celery(
        "mediaforge",
        broker=broker_url,
        backend=broker_url,
        include=["mediaforge.orchestrator.tasks", "mediaforge.orchestrator.maintenance"],
    )

    app.conf.update(
        # Serialization
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        # Routing — priority queues map to batch payload priority field
        task_default_queue="normal",
        task_queues={
            "high":   {"exchange": "high",   "routing_key": "high"},
            "normal": {"exchange": "normal", "routing_key": "normal"},
            "low":    {"exchange": "low",    "routing_key": "low"},
        },
        task_routes={
            "mediaforge.orchestrator.tasks.process_job": {"queue": "high"},
            "mediaforge.orchestrator.maintenance.*": {"queue": "low"},
        },
        # Worker
        worker_concurrency=settings.celery_concurrency,
        worker_prefetch_multiplier=1,
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        # Retry
        task_max_retries=settings.celery_max_retries,
        # Result expiry
        result_expires=60 * 60 * 24,
        # Timezone
        timezone="UTC",
        enable_utc=True,
        # Beat schedule
        beat_schedule={
            "purge-expired-refresh-tokens": {
                "task": "mediaforge.orchestrator.maintenance.purge_expired_tokens",
                "schedule": crontab(minute=0, hour="*/6"),
            },
            "purge-old-audit-logs": {
                "task": "mediaforge.orchestrator.maintenance.purge_old_audit_logs",
                "schedule": crontab(minute=30, hour=2),
            },
        },
    )

    return app


celery_app = create_celery()
