from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_reports_running_orbit_api() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "name": "Orbit",
        "service": "orbit-api",
        "version": "0.0.1",
        "status": "healthy",
    }


def test_root_identifies_the_service() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {
        "name": "Orbit",
        "service": "orbit-api",
        "version": "0.0.1",
    }


def test_openapi_document_and_swagger_ui_are_available() -> None:
    openapi_response = client.get("/openapi.json")
    docs_response = client.get("/docs")

    assert openapi_response.status_code == 200
    assert openapi_response.json()["info"]["title"] == "Orbit API"
    assert openapi_response.json()["info"]["version"] == "0.0.1"
    assert docs_response.status_code == 200
