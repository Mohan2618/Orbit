import hashlib
import hmac
import json
from unittest.mock import Mock

import app.api.routes.integrations as integration_routes
from app.models.github_delivery import GitHubDelivery


def test_signed_github_push_is_enqueued_once(api_client, db_factory, monkeypatch):
    secret = "webhook-test-secret"
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", secret)
    enqueue = Mock()
    monkeypatch.setattr(integration_routes.run_test_run, "delay", enqueue)
    body = json.dumps({"repository": {"html_url": "https://github.com/example/project"}}).encode()
    signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    headers = {
        "X-GitHub-Event": "push",
        "X-GitHub-Delivery": "delivery-1",
        "X-Hub-Signature-256": signature,
    }

    first = api_client.post("/api/v1/integrations/github/webhook", content=body, headers=headers)
    duplicate = api_client.post("/api/v1/integrations/github/webhook", content=body, headers=headers)

    assert first.status_code == 202
    assert first.json()["duplicate"] is False
    assert duplicate.status_code == 202
    assert duplicate.json()["duplicate"] is True
    enqueue.assert_called_once()
    with db_factory() as session:
        assert session.get(GitHubDelivery, "delivery-1") is not None


def test_github_webhook_rejects_invalid_signature(api_client, monkeypatch):
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "configured-secret")
    response = api_client.post(
        "/api/v1/integrations/github/webhook",
        content=b"{}",
        headers={"X-GitHub-Event": "push", "X-GitHub-Delivery": "bad", "X-Hub-Signature-256": "sha256=bad"},
    )
    assert response.status_code == 401


def test_api_key_protects_platform_routes_but_not_signed_webhook(api_client, monkeypatch):
    monkeypatch.setenv("ORBIT_API_KEY", "team-secret")
    assert api_client.get("/api/v1/schedules").status_code == 401
    assert api_client.get("/api/v1/schedules", headers={"Authorization": "Bearer team-secret"}).status_code == 200
    response = api_client.post("/api/v1/integrations/github/webhook", content=b"{}")
    assert response.status_code == 503
