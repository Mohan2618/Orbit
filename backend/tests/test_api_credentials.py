import app.main as main_module
from app.models.api_credential import ApiCredential


def test_admin_can_create_use_and_revoke_team_api_key(api_client, db_factory, monkeypatch):
    monkeypatch.setenv("ORBIT_API_KEY", "administrator-secret")
    monkeypatch.setattr(main_module, "SessionLocal", db_factory)
    headers = {"Authorization": "Bearer administrator-secret"}

    created = api_client.post("/api/v1/admin/api-keys", json={"name": "CI pipeline"}, headers=headers)

    assert created.status_code == 201
    body = created.json()
    assert body["name"] == "CI pipeline"
    assert body["token"].startswith("orbt_")
    assert "key_hash" not in body
    team_headers = {"Authorization": f"Bearer {body['token']}"}
    assert api_client.get("/api/v1/schedules", headers=team_headers).status_code == 200

    revoked = api_client.post(f"/api/v1/admin/api-keys/{body['id']}/revoke", headers=headers)

    assert revoked.status_code == 200
    assert revoked.json()["revoked_at"] is not None
    assert api_client.get("/api/v1/schedules", headers=team_headers).status_code == 401
    with db_factory() as session:
        stored = session.get(ApiCredential, body["id"])
        assert stored is not None
        assert stored.key_hash != body["token"]


def test_team_key_creation_requires_administrator_key(api_client, monkeypatch):
    monkeypatch.setenv("ORBIT_API_KEY", "administrator-secret")
    response = api_client.post("/api/v1/admin/api-keys", json={"name": "blocked"})
    assert response.status_code == 401
