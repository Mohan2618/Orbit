"""Read-only repository discovery using GitHub's public REST API.

This service treats repository files as data. It never checks out or executes
code from the analyzed project.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from urllib.parse import quote, urlsplit

import httpx

from app.schemas.repository import RepositoryIntelligence

GITHUB_API = "https://api.github.com"
GITHUB_API_VERSION = "2026-03-10"
MAX_MANIFEST_SIZE = 64 * 1024
MAX_MANIFESTS = 8
MAX_API_REDIRECTS = 3

MANIFEST_NAMES = {
    "cargo.toml",
    "composer.json",
    "gemfile",
    "go.mod",
    "package.json",
    "pipfile",
    "pyproject.toml",
    "requirements.txt",
}

SKIP_DIRECTORY_NAMES = {
    ".git",
    ".next",
    ".venv",
    "build",
    "dist",
    "node_modules",
    "vendor",
}


class RepositoryNotFound(Exception):
    """The repository is missing or is not publicly accessible."""


class GitHubRateLimited(Exception):
    """GitHub refused the request because of a rate limit or access policy."""


class GitHubUnavailable(Exception):
    """GitHub could not be reached or returned an unexpected error."""


@dataclass(frozen=True)
class GitHubRepository:
    owner: str
    name: str

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"


def parse_github_repository_url(repository_url: str) -> GitHubRepository:
    """Accept only a plain HTTPS github.com/owner/repository URL."""
    try:
        parsed = urlsplit(repository_url.strip())
        parts = [part for part in parsed.path.strip("/").split("/") if part]
        if (
            parsed.scheme.lower() != "https"
            or parsed.hostname is None
            or parsed.hostname.lower() != "github.com"
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port not in (None, 443)
            or parsed.query
            or parsed.fragment
            or len(parts) != 2
        ):
            raise ValueError

        owner, name = parts
        if name.lower().endswith(".git"):
            name = name[:-4]
        if not _valid_slug(owner) or not _valid_slug(name):
            raise ValueError
        return GitHubRepository(owner=owner, name=name)
    except (AttributeError, ValueError) as exc:
        raise ValueError(
            "repository_url must be an HTTPS URL in the form "
            "https://github.com/owner/repository"
        ) from exc


def _valid_slug(value: str) -> bool:
    return value not in {".", ".."} and re.fullmatch(r"[A-Za-z0-9_.-]+", value) is not None


def _is_skipped_path(path: str) -> bool:
    return any(part.lower() in SKIP_DIRECTORY_NAMES for part in path.split("/"))


def _python_package_name(line: str) -> str | None:
    match = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)", line)
    return match.group(1).lower().replace("_", "-") if match else None


def _manifest_dependencies(path: str, content: str) -> set[str]:
    name = path.rsplit("/", 1)[-1].lower()
    dependencies: set[str] = set()
    if name == "requirements.txt":
        for line in content.splitlines():
            line = line.split("#", 1)[0].strip()
            package = _python_package_name(line)
            if package:
                dependencies.add(package)
    elif name == "pyproject.toml":
        try:
            import tomllib

            pyproject = tomllib.loads(content)
        except (ImportError, ValueError):
            return dependencies
        for section in ("project", "tool.poetry"):
            table = pyproject
            for key in section.split("."):
                table = table.get(key, {}) if isinstance(table, dict) else {}
            declared = table.get("dependencies", {}) if isinstance(table, dict) else {}
            if isinstance(declared, dict):
                dependencies.update(
                    str(package).lower().replace("_", "-")
                    for package in declared
                    if package.lower() != "python"
                )
            elif isinstance(declared, list):
                for item in declared:
                    package = _python_package_name(str(item))
                    if package and package != "python":
                        dependencies.add(package)
        project = pyproject.get("project", {})
        optional = project.get("optional-dependencies", {}) if isinstance(project, dict) else {}
        if isinstance(optional, dict):
            for group in optional.values():
                if isinstance(group, list):
                    for item in group:
                        package = _python_package_name(str(item))
                        if package:
                            dependencies.add(package)
        tool = pyproject.get("tool", {})
        poetry = tool.get("poetry", {}) if isinstance(tool, dict) else {}
        if isinstance(poetry, dict):
            for section in ("dev-dependencies",):
                declared = poetry.get(section, {})
                if isinstance(declared, dict):
                    dependencies.update(
                        str(package).lower().replace("_", "-")
                        for package in declared
                        if package.lower() != "python"
                    )
            groups = poetry.get("group", {})
            if isinstance(groups, dict):
                for group in groups.values():
                    declared = group.get("dependencies", {}) if isinstance(group, dict) else {}
                    if isinstance(declared, dict):
                        dependencies.update(
                            str(package).lower().replace("_", "-")
                            for package in declared
                            if package.lower() != "python"
                        )
    elif name == "package.json":
        try:
            package_data = json.loads(content)
        except json.JSONDecodeError:
            return dependencies
        for section in ("dependencies", "devDependencies", "peerDependencies"):
            declared = package_data.get(section, {})
            if isinstance(declared, dict):
                dependencies.update(str(package).lower() for package in declared)
    elif name == "gemfile":
        dependencies.update(
            match.group(1).lower()
            for match in re.finditer(r"^\s*gem\s+['\"]([^'\"]+)", content, re.MULTILINE)
        )
    elif name == "go.mod":
        dependencies.update(
            match.group(1).rsplit("/", 1)[-1].lower()
            for match in re.finditer(r"^\s*([\w./-]+)\s+v[\w.+-]+", content, re.MULTILINE)
        )
    elif name == "cargo.toml":
        try:
            import tomllib

            cargo = tomllib.loads(content)
        except (ImportError, ValueError):
            return dependencies
        for section in ("dependencies", "dev-dependencies", "build-dependencies"):
            declared = cargo.get(section, {})
            if isinstance(declared, dict):
                dependencies.update(str(package).lower().replace("_", "-") for package in declared)
    elif name == "composer.json":
        try:
            composer = json.loads(content)
        except json.JSONDecodeError:
            return dependencies
        for section in ("require", "require-dev"):
            declared = composer.get(section, {})
            if isinstance(declared, dict):
                dependencies.update(str(package).lower() for package in declared)
    elif name == "pipfile":
        # Pipfile entries are TOML tables. Keep detection intentionally simple;
        # project metadata and the other common manifests provide richer data.
        in_dependency_section = False
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("["):
                in_dependency_section = stripped in {"[packages]", "[dev-packages]"}
            elif in_dependency_section and "=" in stripped and not stripped.startswith("#"):
                dependencies.add(stripped.split("=", 1)[0].strip().lower().replace("_", "-"))
    return dependencies


def _detect_frameworks(dependencies: set[str]) -> list[str]:
    candidates = (
        ("fastapi", "FastAPI"),
        ("django", "Django"),
        ("flask", "Flask"),
        ("express", "Express"),
        ("next", "Next.js"),
        ("react", "React"),
        ("vue", "Vue"),
        ("svelte", "Svelte"),
        ("rails", "Ruby on Rails"),
        ("laravel/framework", "Laravel"),
    )
    return [label for package, label in candidates if package in dependencies]


def _detect_test_frameworks(
    dependencies: set[str], paths: set[str]
) -> list[str]:
    detected: set[str] = set()
    if "pytest" in dependencies or any(path.rsplit("/", 1)[-1] in {"pytest.ini", "conftest.py"} for path in paths):
        detected.add("pytest")
    if "jest" in dependencies:
        detected.add("Jest")
    if "vitest" in dependencies:
        detected.add("Vitest")
    if "playwright" in dependencies or "@playwright/test" in dependencies:
        detected.add("Playwright")
    if "cypress" in dependencies:
        detected.add("Cypress")
    if any(path.rsplit("/", 1)[-1] == "manage.py" for path in paths):
        # Django's test runner is part of the framework and needs no dependency.
        if "django" in dependencies:
            detected.add("Django test runner")
    return sorted(detected)


def _detect_entry_points(paths: set[str]) -> list[str]:
    conventional = {
        "app.py",
        "main.py",
        "manage.py",
        "index.js",
        "index.ts",
        "server.js",
        "server.ts",
    }
    return sorted(
        path
        for path in paths
        if path in conventional
        or path in {"app/main.py", "src/main.py", "src/main.ts", "src/index.ts", "cmd/main.go"}
    )


class GitHubRepositoryAnalyzer:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    async def analyze(self, repository_url: str) -> RepositoryIntelligence:
        repository = parse_github_repository_url(repository_url)
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": GITHUB_API_VERSION,
            "User-Agent": "Orbit-Repository-Intelligence/0.1.0",
        }

        async with httpx.AsyncClient(
            base_url=GITHUB_API,
            headers=headers,
            timeout=httpx.Timeout(8.0),
            follow_redirects=False,
            transport=self._transport,
        ) as client:
            metadata = await self._get_json(client, f"/repos/{quote(repository.owner)}/{quote(repository.name)}")
            canonical_name = metadata.get("full_name")
            if isinstance(canonical_name, str):
                repository = parse_github_repository_url(f"https://github.com/{canonical_name}")
            languages = await self._get_json(client, f"/repos/{quote(repository.owner)}/{quote(repository.name)}/languages")
            default_branch = metadata.get("default_branch")
            if not isinstance(default_branch, str) or not default_branch:
                raise GitHubUnavailable("GitHub returned repository metadata without a default branch.")
            tree = await self._get_json(
                client,
                f"/repos/{quote(repository.owner)}/{quote(repository.name)}/git/trees/{quote(default_branch, safe='')}?recursive=1",
            )

            raw_tree = tree.get("tree", [])
            if not isinstance(raw_tree, list):
                raise GitHubUnavailable("GitHub returned an invalid repository file tree.")
            files = [
                item
                for item in raw_tree
                if isinstance(item, dict)
                and item.get("type") == "blob"
                and isinstance(item.get("path"), str)
                and not _is_skipped_path(item["path"])
                and item.get("mode") != "120000"
            ]
            paths = {item["path"] for item in files}
            manifests = [
                item
                for item in files
                if item["path"].rsplit("/", 1)[-1].lower() in MANIFEST_NAMES
                and isinstance(item.get("size", 0), int)
                and item.get("size", 0) <= MAX_MANIFEST_SIZE
            ][:MAX_MANIFESTS]
            dependencies: set[str] = set()
            manifest_paths: list[str] = []
            manifest_contents = await asyncio.gather(
                *(
                    self._get_manifest(client, repository, default_branch, manifest["path"])
                    for manifest in manifests
                )
            )
            for manifest, content in zip(manifests, manifest_contents):
                if content is None:
                    continue
                path = manifest["path"]
                manifest_paths.append(path)
                dependencies.update(_manifest_dependencies(path, content))

        return RepositoryIntelligence(
            full_name=str(metadata.get("full_name") or repository.full_name),
            repository_url=str(metadata.get("html_url") or f"https://github.com/{repository.full_name}"),
            description=metadata.get("description"),
            default_branch=default_branch,
            languages=sorted(
                (name for name, size in languages.items() if isinstance(size, int) and size > 0),
                key=lambda language: (-languages[language], language.lower()),
            ) if isinstance(languages, dict) else [],
            frameworks=_detect_frameworks(dependencies),
            dependencies=sorted(dependencies),
            test_frameworks=_detect_test_frameworks(dependencies, paths),
            entry_points=_detect_entry_points(paths),
            docker_detected=any(
                path.rsplit("/", 1)[-1].lower() == "dockerfile"
                or path.rsplit("/", 1)[-1].lower().startswith("docker-compose.")
                or path.rsplit("/", 1)[-1].lower() in {"compose.yml", "compose.yaml"}
                for path in paths
            ),
            manifest_files=sorted(manifest_paths),
            analyzed_files=len(paths),
            file_tree_truncated=bool(tree.get("truncated", False)),
        )

    async def _get_json(self, client: httpx.AsyncClient, path: str) -> dict:
        request_url: str | httpx.URL = path
        for redirect_count in range(MAX_API_REDIRECTS + 1):
            try:
                response = await client.get(request_url)
            except httpx.TimeoutException as exc:
                raise GitHubUnavailable("GitHub request timed out. Please try again.") from exc
            except httpx.RequestError as exc:
                raise GitHubUnavailable("Could not connect to GitHub. Please try again.") from exc
            if response.is_redirect:
                location = response.headers.get("location")
                if not location or redirect_count == MAX_API_REDIRECTS:
                    raise GitHubUnavailable("GitHub returned too many redirects.")
                redirect_url = response.request.url.join(location)
                if redirect_url.scheme != "https" or redirect_url.host != "api.github.com":
                    raise GitHubUnavailable("GitHub returned a redirect outside the GitHub API host.")
                request_url = redirect_url
                continue
            break
        if response.status_code == 404:
            raise RepositoryNotFound("Repository not found or not publicly accessible.")
        if response.status_code in {403, 429}:
            raise GitHubRateLimited("GitHub denied the request or the public API rate limit was reached.")
        if response.status_code >= 500:
            raise GitHubUnavailable("GitHub is temporarily unavailable. Please try again.")
        if response.status_code >= 400:
            raise GitHubUnavailable("GitHub rejected the repository analysis request.")
        try:
            payload = response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise GitHubUnavailable("GitHub returned an invalid response.") from exc
        if not isinstance(payload, dict):
            raise GitHubUnavailable("GitHub returned an invalid response.")
        return payload

    async def _get_manifest(
        self,
        client: httpx.AsyncClient,
        repository: GitHubRepository,
        branch: str,
        path: str,
    ) -> str | None:
        encoded_path = "/".join(quote(part, safe="") for part in path.split("/"))
        endpoint = (
            f"/repos/{quote(repository.owner)}/{quote(repository.name)}/contents/"
            f"{encoded_path}?ref={quote(branch, safe='')}"
        )
        try:
            response = await client.get(endpoint, headers={"Accept": "application/vnd.github.raw+json"})
        except httpx.RequestError:
            return None
        if response.status_code != 200 or len(response.content) > MAX_MANIFEST_SIZE:
            return None
        return response.text
