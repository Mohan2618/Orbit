from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.run_schedule import RunSchedule
from app.schemas.run_schedule import ScheduleRequest, ScheduleResponse
from app.services.repository_intelligence import parse_github_repository_url

router = APIRouter(prefix="/api/v1/schedules", tags=["schedules"])
MAX_SCHEDULES = 200


@router.post("", response_model=ScheduleResponse, status_code=status.HTTP_201_CREATED)
def create_schedule(request: ScheduleRequest, session: Session = Depends(get_db)) -> RunSchedule:
    try:
        parse_github_repository_url(request.repository_url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    schedule_count = session.scalar(select(func.count()).select_from(RunSchedule)) or 0
    if schedule_count >= MAX_SCHEDULES:
        raise HTTPException(status_code=429, detail="The schedule limit has been reached.")
    schedule = RunSchedule(
        repository_url=request.repository_url.strip(),
        interval_minutes=request.interval_minutes,
        next_run_at=datetime.now(timezone.utc) + timedelta(minutes=request.interval_minutes),
    )
    session.add(schedule)
    session.commit()
    session.refresh(schedule)
    return schedule


@router.get("", response_model=list[ScheduleResponse])
def list_schedules(session: Session = Depends(get_db)) -> list[RunSchedule]:
    return list(session.scalars(select(RunSchedule).order_by(RunSchedule.created_at.desc()).limit(200)))


@router.delete("/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_schedule(schedule_id: str, session: Session = Depends(get_db)) -> None:
    schedule = session.get(RunSchedule, schedule_id)
    if schedule is None:
        raise HTTPException(status_code=404, detail="Schedule not found.")
    session.delete(schedule)
    session.commit()
