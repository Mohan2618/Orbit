"""Fetch public GitHub source archives without executing repository contents."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path, PurePosixPath
import tarfile
from urllib.parse import quote

import httpx

from app.services.repository_intelligence import (
    GITHUB_API_VERSION,
    GitHubRepositoryAnalyzer,
    GitHubUnavailable,
    parse_github_repository_url,
)

MAX_ARCHIVE_BYTES = 50 * 1024 * 1024
MAX_SOURCE_BYTES = 256 * 1024 * 1024
MAX_SOURCE_FILES = 20000
MAX_ARCHIVE_ENTRIES = 50000
ARCHIVE_HOSTS = {"api.github.com", "codeload.github.com"}


async def download_repository(repository_url: str, destination: Path) -> dict:
    """Fetch and safely extract a public repo; return a compact discovery report."""
    initial = parse_github_repository_url(repository_url)
    discovery = await GitHubRepositoryAnalyzer().analyze(repository_url)
    canonical = parse_github_repository_url(discovery.repository_url)
    endpoint = (
        f"https://api.github.com/repos/{quote(canonical.owner)}/{quote(canonical.name)}"
        f"/tarball/{quote(discovery.default_branch, safe='')}"
    )
    archive = await _fetch_archive(endpoint)
    destination.mkdir(parents=True, exist_ok=True)
    _extract_source_archive(archive, destination)
    return {
        "full_name": discovery.full_name,
        "repository_url": discovery.repository_url,
        "default_branch": discovery.default_branch,
        "languages": discovery.languages,
        "dependencies": _python_dependencies(destination, discovery.manifest_files),
        "analyzed_files": discovery.analyzed_files,
        "requested_repository": initial.full_name,
    }


async def _fetch_archive(endpoint: str) -> bytes:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
        "User-Agent": "Orbit-QA-Runner/1.0.0",
    }
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0), follow_redirects=False) as client:
        request_url = httpx.URL(endpoint)
        for redirect_count in range(4):
            try:
                async with client.stream("GET", request_url, headers=headers) as response:
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location or redirect_count >= 3:
                            raise GitHubUnavailable("GitHub returned too many archive redirects.")
                        redirect_url = httpx.URL(request_url).join(location)
                        if (
                            redirect_url.scheme != "https"
                            or redirect_url.host not in ARCHIVE_HOSTS
                            or redirect_url.port not in (None, 443)
                            or bool(redirect_url.username)
                            or bool(redirect_url.password)
                        ):
                            raise GitHubUnavailable("GitHub returned an unsafe archive redirect.")
                        request_url = redirect_url
                        continue
                    if response.status_code == 404:
                        raise GitHubUnavailable("The public repository archive could not be found.")
                    if response.status_code in {403, 429}:
                        raise GitHubUnavailable("GitHub denied the archive request or its rate limit was reached.")
                    if response.status_code >= 400:
                        raise GitHubUnavailable("GitHub could not provide the repository archive.")
                    size_header = response.headers.get("content-length")
                    if size_header and int(size_header) > MAX_ARCHIVE_BYTES:
                        raise GitHubUnavailable("The repository archive exceeds the 50 MiB limit.")
                    archive = bytearray()
                    async for chunk in response.aiter_bytes():
                        archive.extend(chunk)
                        if len(archive) > MAX_ARCHIVE_BYTES:
                            raise GitHubUnavailable("The repository archive exceeds the 50 MiB limit.")
                    return bytes(archive)
            except httpx.TimeoutException as exc:
                raise GitHubUnavailable("The repository archive request timed out.") from exc
            except httpx.RequestError as exc:
                raise GitHubUnavailable("Could not download the public repository archive.") from exc
    raise GitHubUnavailable("GitHub returned too many archive redirects.")


def _extract_source_archive(archive: bytes, destination: Path) -> None:
    """Extract regular files only, rejecting traversal and oversized archives."""
    destination = destination.resolve()
    total_bytes = 0
    extracted_files = 0
    entry_count = 0
    seen_paths: set[Path] = set()
    try:
        with tarfile.open(fileobj=BytesIO(archive), mode="r:gz") as tar:
            for member in tar:
                entry_count += 1
                if entry_count > MAX_ARCHIVE_ENTRIES:
                    raise GitHubUnavailable("The repository archive contains too many entries.")
                parts = PurePosixPath(member.name).parts
                if not parts or parts[0] in {"", ".", ".."} or ".." in parts or PurePosixPath(member.name).is_absolute():
                    raise GitHubUnavailable("The repository archive contains an unsafe path.")
                if len(parts) == 1:
                    continue
                if member.isdir():
                    continue
                if not member.isfile():
                    # Symlinks, hardlinks, devices, and other special entries are ignored.
                    continue
                total_bytes += member.size
                extracted_files += 1
                if total_bytes > MAX_SOURCE_BYTES or extracted_files > MAX_SOURCE_FILES:
                    raise GitHubUnavailable("The repository source exceeds the extraction limits.")
                relative = Path(*parts[1:])
                target = (destination / relative).resolve()
                if not target.is_relative_to(destination):
                    raise GitHubUnavailable("The repository archive contains an unsafe path.")
                if target in seen_paths:
                    continue
                seen_paths.add(target)
                target.parent.mkdir(parents=True, exist_ok=True)
                source_file = tar.extractfile(member)
                if source_file is None:
                    continue
                with source_file, target.open("wb") as target_file:
                    remaining = member.size
                    while remaining:
                        chunk = source_file.read(min(1024 * 1024, remaining))
                        if not chunk:
                            raise GitHubUnavailable("The repository archive ended unexpectedly.")
                        target_file.write(chunk)
                        remaining -= len(chunk)
                target.chmod(0o644 if member.mode & 0o111 == 0 else 0o755)
    except (tarfile.TarError, OSError, ValueError) as exc:
        raise GitHubUnavailable("The repository archive could not be safely extracted.") from exc


def _python_dependencies(source: Path, manifest_paths: list[str]) -> list[str]:
    from app.services.repository_intelligence import _manifest_dependencies

    dependencies: set[str] = set()
    allowed_manifest_names = {"requirements.txt", "pyproject.toml", "pipfile"}
    for manifest_path in manifest_paths:
        if manifest_path.rsplit("/", 1)[-1].lower() not in allowed_manifest_names:
            continue
        manifest = source / Path(*manifest_path.split("/"))
        if not manifest.is_file() or manifest.stat().st_size > 64 * 1024:
            continue
        try:
            content = manifest.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        dependencies.update(_manifest_dependencies(manifest_path, content))

    safe = {
        name
        for name in dependencies
        if len(name) <= 100
        and name
        and name[0].isalnum()
        and all(character.isalnum() or character in "._-" for character in name)
    }
    if len(safe) > 40:
        raise GitHubUnavailable("The repository declares more than 40 Python dependencies.")
    return sorted(safe)
