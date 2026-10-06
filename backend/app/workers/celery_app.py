import os

from celery import Celery

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery("orbit", broker=REDIS_URL)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_ignore_result=True,
    broker_connection_retry_on_startup=True,
    task_routes={"app.workers.tasks.run_test_run": {"queue": "qa-runs"}},
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_soft_time_limit=780,
    task_time_limit=840,
    beat_schedule={
        "dispatch-due-orbit-schedules": {
            "task": "app.workers.tasks.dispatch_due_schedules",
            "schedule": 60.0,
            "options": {"queue": "qa-runs"},
        }
    },
)

celery_app.autodiscover_tasks(["app.workers"])
