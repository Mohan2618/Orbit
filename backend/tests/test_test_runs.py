from unittest.mock import Mock

import pytest

import app.api.routes.test_runs as test_run_routes
import app.models.test_run as test_run_model


def test_create_test_run_persists_and_enqueues(api_client, db_factory, monkeypatch):
    enqueue = Mock()
    monkeypatch.setattr(test_run_routes.run_test_run, "delay", enqueue)

    response = api_client.post(
        "/api/v1/test-runs",
        json={"repository_url": "https://github.com/example/project"},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    assert body["repository_url"] == "https://github.com/example/project"
    enqueue.assert_called_once_with(body["id"])

    with db_factory() as session:
        stored = session.get(test_run_model.TestRun, body["id"])
        assert stored is not None
        assert stored.status == "queued"


def test_get_test_run_reports_missing_id(api_client):
    response = api_client.get("/api/v1/test-runs/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404
    assert response.json()["detail"] == "Test run not found."


@pytest.mark.parametrize(
    "repository_url",
    ["http://github.com/example/project", "https://example.com/owner/project"],
)
def test_create_test_run_rejects_unsupported_urls(api_client, repository_url):
    response = api_client.post("/api/v1/test-runs", json={"repository_url": repository_url})

    assert response.status_code == 422


def test_queue_failure_marks_persisted_run_failed(api_client, db_factory, monkeypatch):
    enqueue = Mock(side_effect=ConnectionError("broker unavailable"))
    monkeypatch.setattr(test_run_routes.run_test_run, "delay", enqueue)

    response = api_client.post(
        "/api/v1/test-runs",
        json={"repository_url": "https://github.com/example/project"},
    )

    assert response.status_code == 503
    run_id = enqueue.call_args.args[0]
    with db_factory() as session:
        stored = session.get(test_run_model.TestRun, run_id)
        assert stored is not None
        assert stored.status == "failed"
        assert stored.error_message == "The QA worker queue is unavailable. Please try again."


def test_readiness_checks_database_and_queue(api_client, monkeypatch):
    fake_queue = Mock()
    monkeypatch.setattr("app.api.routes.health.Redis.from_url", Mock(return_value=fake_queue))

    response = api_client.get("/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    fake_queue.ping.assert_called_once()
    fake_queue.close.assert_called_once()
