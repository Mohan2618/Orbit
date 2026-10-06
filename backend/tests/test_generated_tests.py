from unittest.mock import Mock

import pytest

import app.api.routes.test_generation as generation_routes
import app.api.routes.test_runs as run_routes
from app.models.generated_test import GeneratedTest


def test_generated_test_requires_explicit_source_sharing_opt_in(api_client):
    response = api_client.post(
        "/api/v1/generated-tests",
        json={
            "repository_url": "https://github.com/example/project",
            "source_path": "src/math.py",
            "share_source_with_model": False,
        },
    )
    assert response.status_code == 400


@pytest.mark.parametrize("path", ["../secrets.py", "C:/secrets.py", "src\\..\\secrets.py", "/root.py"])
def test_generation_rejects_unsafe_paths(api_client, path):
    response = api_client.post(
        "/api/v1/generated-tests",
        json={
            "repository_url": "https://github.com/example/project",
            "source_path": path,
            "share_source_with_model": True,
        },
    )
    assert response.status_code == 422


def test_candidate_must_be_approved_and_match_repository(api_client, db_factory, monkeypatch):
    candidate = GeneratedTest(
        repository_url="https://github.com/example/project",
        source_path="src/math.py",
        model="test-model",
        source_digest="0" * 64,
        source_shared_with_model=True,
        test_code="def test_example():\n    assert 1 + 1 == 2\n",
        review_findings=[],
        approved=False,
    )
    with db_factory() as session:
        session.add(candidate)
        session.commit()
        session.refresh(candidate)
        candidate_id = candidate.id
    enqueue = Mock()
    monkeypatch.setattr(run_routes.run_test_run, "delay", enqueue)
    rejected = api_client.post(
        "/api/v1/test-runs",
        json={"repository_url": "https://github.com/example/project", "generated_test_id": candidate_id},
    )
    assert rejected.status_code == 422
    approved = api_client.post(f"/api/v1/generated-tests/{candidate_id}/approve")
    assert approved.status_code == 200
    assert approved.json()["approved_at"] is not None
    wrong_repo = api_client.post(
        "/api/v1/test-runs",
        json={"repository_url": "https://github.com/example/other", "generated_test_id": candidate_id},
    )
    assert wrong_repo.status_code == 422
    accepted = api_client.post(
        "/api/v1/test-runs",
        json={"repository_url": "https://github.com/example/project", "generated_test_id": candidate_id},
    )
    assert accepted.status_code == 202
    assert accepted.json()["generated_test_id"] == candidate_id
    enqueue.assert_called_once_with(accepted.json()["id"])


@pytest.mark.parametrize(
    "code,rule",
    [
        ("import subprocess\ndef test_x(): pass", "blocked_import"),
        ("def test_x():\n    eval('1')", "blocked_call"),
        ("def test_x(: pass", "syntax"),
    ],
)
def test_generation_safety_review_rejects_unsafe_or_invalid_code(code, rule):
    from app.services.test_generation import validate_generated_test

    assert validate_generated_test(code)[0]["rule"] == rule


def test_generation_route_persists_review_candidate(api_client, monkeypatch, tmp_path):
    async def fetch_repository(_url, source):
        source.mkdir(parents=True)
        (source / "src").mkdir()
        (source / "src" / "calculator.py").write_text("def add(a, b): return a + b\n", encoding="utf-8")
        return {}

    async def generate(_code, _path):
        return "def test_add():\n    assert 1 + 2 == 3\n", "configured-model", []

    monkeypatch.setattr(generation_routes, "download_repository", fetch_repository)
    monkeypatch.setattr(generation_routes, "generate_tests", generate)
    response = api_client.post(
        "/api/v1/generated-tests",
        json={
            "repository_url": "https://github.com/example/project",
            "source_path": "src/calculator.py",
            "share_source_with_model": True,
        },
    )
    assert response.status_code == 201
    assert response.json()["approved"] is False
    assert response.json()["model"] == "configured-model"
    assert response.json()["source_shared_with_model"] is True
    assert len(response.json()["source_digest"]) == 64
