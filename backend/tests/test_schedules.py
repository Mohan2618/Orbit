from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import app.models.test_run as test_run_model
from app.models.run_schedule import RunSchedule
from app.workers import tasks


def test_schedule_lifecycle_and_minimum_interval(api_client):
    invalid = api_client.post(
        "/api/v1/schedules",
        json={"repository_url": "https://github.com/example/project", "interval_minutes": 5},
    )
    assert invalid.status_code == 422
    created = api_client.post(
        "/api/v1/schedules",
        json={"repository_url": "https://github.com/example/project", "interval_minutes": 60},
    )
    assert created.status_code == 201
    schedule_id = created.json()["id"]
    assert len(api_client.get("/api/v1/schedules").json()) == 1
    assert api_client.delete(f"/api/v1/schedules/{schedule_id}").status_code == 204
    assert api_client.delete(f"/api/v1/schedules/{schedule_id}").status_code == 404


def test_due_schedule_creates_and_enqueues_run(api_client, db_factory, monkeypatch):
    with db_factory() as session:
        schedule = RunSchedule(
            repository_url="https://github.com/example/project",
            interval_minutes=30,
            next_run_at=datetime.now(UTC) - timedelta(minutes=1),
        )
        session.add(schedule)
        session.commit()
    enqueue = Mock()
    monkeypatch.setattr(tasks, "SessionLocal", db_factory)
    monkeypatch.setattr(tasks.run_test_run, "delay", enqueue)

    assert tasks.dispatch_due_schedules.run() == 1

    enqueue.assert_called_once()
    with db_factory() as session:
        run = session.get(test_run_model.TestRun, enqueue.call_args.args[0])
        updated = session.query(RunSchedule).one()
        assert run.repository_url == "https://github.com/example/project"
        assert updated.next_run_at > datetime.now(UTC).replace(tzinfo=None)
