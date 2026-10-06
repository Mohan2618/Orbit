from datetime import datetime

import app.services.qa_execution as qa_execution
import app.models.test_run as test_run_model
from app.workers.tasks import run_test_run


def test_worker_marks_completed_pytest_run_succeeded(db_factory, monkeypatch):
    with db_factory() as session:
        test_run = test_run_model.TestRun(repository_url="https://github.com/example/project")
        session.add(test_run)
        session.commit()
        run_id = test_run.id

    monkeypatch.setattr("app.workers.tasks.SessionLocal", db_factory)
    monkeypatch.setattr(
        qa_execution,
        "execute_test_run",
        lambda _run_id: {"outcome": "passed", "counts": {"passed": 3}},
    )

    run_test_run.apply(args=[run_id], throw=True)

    with db_factory() as session:
        completed = session.get(test_run_model.TestRun, run_id)
        assert completed is not None
        assert completed.status == "completed"
        assert completed.started_at is not None
        assert isinstance(completed.completed_at, datetime)
        assert completed.result == {"outcome": "passed", "counts": {"passed": 3}}


def test_worker_marks_test_failure_and_keeps_report(db_factory, monkeypatch):
    with db_factory() as session:
        test_run = test_run_model.TestRun(repository_url="https://github.com/example/project")
        session.add(test_run)
        session.commit()
        run_id = test_run.id

    monkeypatch.setattr("app.workers.tasks.SessionLocal", db_factory)
    monkeypatch.setattr(
        qa_execution,
        "execute_test_run",
        lambda _run_id: {
            "outcome": "failed",
            "counts": {"failed": 1},
            "error_message": None,
        },
    )

    run_test_run.apply(args=[run_id], throw=True)

    with db_factory() as session:
        completed = session.get(test_run_model.TestRun, run_id)
        assert completed is not None
        assert completed.status == "completed"
        assert completed.result["counts"] == {"failed": 1}
