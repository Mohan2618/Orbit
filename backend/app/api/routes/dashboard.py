from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.run_schedule import RunSchedule
from app.models.test_run import TestRun

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


@router.get("/summary")
def dashboard_summary(session: Session = Depends(get_db)) -> dict:
    counts = dict(session.execute(select(TestRun.status, func.count()).group_by(TestRun.status)).all())
    recent = session.scalars(select(TestRun).order_by(TestRun.created_at.desc()).limit(10)).all()
    return {
        "runs_by_status": counts,
        "total_runs": sum(counts.values()),
        "active_schedules": session.scalar(select(func.count()).select_from(RunSchedule)) or 0,
        "recent_runs": [
            {"id": run.id, "repository_url": run.repository_url, "status": run.status,
             "outcome": (run.result or {}).get("outcome"), "created_at": run.created_at,
             "completed_at": run.completed_at}
            for run in recent
        ],
    }
