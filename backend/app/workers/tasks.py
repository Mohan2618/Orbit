from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.test_run import TestRun
from app.models.run_schedule import RunSchedule
from app.workers.celery_app import celery_app


@celery_app.task(bind=True, name="app.workers.tasks.run_test_run")
def run_test_run(self, test_run_id: str) -> None:
    """Execute a QA run in a disposable, restricted runner container."""
    from app.services.qa_execution import execute_test_run

    redelivered = bool((self.request.delivery_info or {}).get("redelivered"))
    with SessionLocal() as session:
        test_run = session.scalar(select(TestRun).where(TestRun.id == test_run_id))
        if test_run is None or test_run.status not in {"queued", "running"}:
            return
        if test_run.status == "running" and not redelivered:
            return
        test_run.status = "running"
        test_run.started_at = datetime.now(timezone.utc)
        session.commit()

    try:
        report = execute_test_run(test_run_id)
    except Exception as exc:
        with SessionLocal() as session:
            test_run = session.scalar(select(TestRun).where(TestRun.id == test_run_id))
            if test_run is not None:
                test_run.status = "failed"
                test_run.error_message = str(exc)[:2000]
                test_run.completed_at = datetime.now(timezone.utc)
                session.commit()
        return

    with SessionLocal() as session:
        test_run = session.scalar(select(TestRun).where(TestRun.id == test_run_id))
        if test_run is not None:
            test_run.result = report
            test_run.status = "completed"
            test_run.error_message = report.get("error_message")
            test_run.completed_at = datetime.now(timezone.utc)
            session.commit()


@celery_app.task(name="app.workers.tasks.dispatch_due_schedules")
def dispatch_due_schedules() -> int:
    """Create at most one run per due schedule, using a row lock to avoid duplicate beat dispatches."""
    now = datetime.now(timezone.utc)
    run_ids = []
    with SessionLocal() as session:
        due = session.scalars(
            select(RunSchedule)
            .where(RunSchedule.enabled.is_(True), RunSchedule.next_run_at <= now)
            .order_by(RunSchedule.next_run_at)
            .limit(100)
            .with_for_update(skip_locked=True)
        ).all()
        for schedule in due:
            run = TestRun(repository_url=schedule.repository_url)
            session.add(run)
            session.flush()
            schedule.next_run_at = now + timedelta(minutes=schedule.interval_minutes)
            run_ids.append(run.id)
        session.commit()
    for run_id in run_ids:
        try:
            run_test_run.delay(run_id)
        except Exception:
            with SessionLocal() as session:
                run = session.get(TestRun, run_id)
                if run is not None:
                    run.status = "failed"
                    run.error_message = "The QA worker queue is unavailable."
                    run.completed_at = datetime.now(timezone.utc)
                    session.commit()
    return len(run_ids)
