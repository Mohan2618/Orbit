import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.routes.repositories import get_repository_analyzer
from app.main import app
from app.services.repository_intelligence import (
    GitHubRepositoryAnalyzer,
    _detect_frameworks,
    _detect_test_frameworks,
    _manifest_dependencies,
    parse_github_repository_url,
)

client = TestClient(app)


def test_github_url_parser_accepts_https_repository_url() -> None:
    repository = parse_github_repository_url("https://github.com/Example/project.git/")

    assert repository.full_name == "Example/project"


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/owner/repo",
        "https://github.com.evil.example/owner/repo",
        "https://user:password@github.com/owner/repo",
        "https://github.com/owner/repo/tree/main",
        "https://127.0.0.1/owner/repo",
    ],
)
def test_github_url_parser_rejects_non_repository_urls(url: str) -> None:
    with pytest.raises(ValueError):
        parse_github_repository_url(url)


def test_pyproject_dependency_detection_includes_test_tools() -> None:
    dependencies = _manifest_dependencies(
        "pyproject.toml",
        """
[project]
dependencies = ["fastapi>=0.100"]

[project.optional-dependencies]
test = ["pytest>=8"]

[tool.poetry.group.dev.dependencies]
ruff = "^0.5"
""",
    )

    assert dependencies == {"fastapi", "pytest", "ruff"}
    assert _detect_frameworks(dependencies) == ["FastAPI"]
    assert _detect_test_frameworks(dependencies, set()) == ["pytest"]


def test_python_requirements_ignore_pip_options_and_unsafe_urls() -> None:
    dependencies = _manifest_dependencies(
        "requirements.txt",
        """
-r nested.txt
--index-url https://packages.example.invalid/simple
git+https://example.invalid/project.git#egg=untrusted
fastapi @ https://files.example.invalid/fastapi.whl
requests>=2.0
""",
    )

    assert dependencies == {"fastapi", "requests"}


def test_analyze_endpoint_returns_repository_intelligence() -> None:
    async def github_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/repos/example/service":
            return httpx.Response(
                301,
                headers={"Location": "https://api.github.com/repositories/42"},
            )
        if request.url.path == "/repositories/42":
            return httpx.Response(
                200,
                json={
                    "full_name": "example/service",
                    "html_url": "https://github.com/example/service",
                    "description": "A demo API",
                    "default_branch": "main",
                },
            )
        if request.url.path == "/repos/example/service/languages":
            return httpx.Response(200, json={"Python": 3000, "HTML": 100})
        if request.url.path == "/repos/example/service/git/trees/main":
            return httpx.Response(
                200,
                json={
                    "truncated": False,
                    "tree": [
                        {"path": "app/main.py", "type": "blob", "mode": "100644", "size": 20},
                        {"path": "requirements.txt", "type": "blob", "mode": "100644", "size": 32},
                        {"path": "pytest.ini", "type": "blob", "mode": "100644", "size": 10},
                        {"path": "Dockerfile", "type": "blob", "mode": "100644", "size": 20},
                        {"path": "node_modules/ignored/package.json", "type": "blob", "mode": "100644", "size": 20},
                    ],
                },
            )
        if request.url.path == "/repos/example/service/contents/requirements.txt":
            return httpx.Response(200, text="fastapi>=0.100\npytest>=8\n")
        raise AssertionError(f"Unexpected GitHub request: {request.url}")

    analyzer = GitHubRepositoryAnalyzer(transport=httpx.MockTransport(github_handler))
    app.dependency_overrides[get_repository_analyzer] = lambda: analyzer
    try:
        response = client.post(
            "/api/v1/repositories/analyze",
            json={"repository_url": "https://github.com/example/service"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "full_name": "example/service",
        "repository_url": "https://github.com/example/service",
        "description": "A demo API",
        "default_branch": "main",
        "languages": ["Python", "HTML"],
        "frameworks": ["FastAPI"],
        "dependencies": ["fastapi", "pytest"],
        "test_frameworks": ["pytest"],
        "entry_points": ["app/main.py"],
        "docker_detected": True,
        "manifest_files": ["requirements.txt"],
        "analyzed_files": 4,
        "file_tree_truncated": False,
    }


def test_analyze_endpoint_rejects_arbitrary_hosts() -> None:
    response = client.post(
        "/api/v1/repositories/analyze",
        json={"repository_url": "https://example.com/owner/repo"},
    )

    assert response.status_code == 422
    assert "github.com/owner/repository" in response.json()["detail"]


def test_analyze_endpoint_reports_missing_public_repository() -> None:
    async def missing_repository_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "Not Found"})

    analyzer = GitHubRepositoryAnalyzer(transport=httpx.MockTransport(missing_repository_handler))
    app.dependency_overrides[get_repository_analyzer] = lambda: analyzer
    try:
        response = client.post(
            "/api/v1/repositories/analyze",
            json={"repository_url": "https://github.com/missing/repository"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json()["detail"] == "Repository not found or not publicly accessible."


def test_analyze_endpoint_rejects_redirects_outside_github_api() -> None:
    async def external_redirect_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(301, headers={"Location": "https://example.com/redirect"})

    analyzer = GitHubRepositoryAnalyzer(transport=httpx.MockTransport(external_redirect_handler))
    app.dependency_overrides[get_repository_analyzer] = lambda: analyzer
    try:
        response = client.post(
            "/api/v1/repositories/analyze",
            json={"repository_url": "https://github.com/example/repository"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 502
    assert "outside the GitHub API host" in response.json()["detail"]


def test_analyze_endpoint_reports_github_rate_limit() -> None:
    async def rate_limited_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"message": "API rate limit exceeded"})

    analyzer = GitHubRepositoryAnalyzer(transport=httpx.MockTransport(rate_limited_handler))
    app.dependency_overrides[get_repository_analyzer] = lambda: analyzer
    try:
        response = client.post(
            "/api/v1/repositories/analyze",
            json={"repository_url": "https://github.com/example/repository"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert "rate limit" in response.json()["detail"]
