# Orbit 0.1 — Repository intelligence

## User flow

Submit a public GitHub repository URL to `POST /api/v1/repositories/analyze`. Orbit validates that the URL names a repository on `github.com`, then reads repository metadata, the language summary, the default branch's Git tree, and selected dependency manifests through the GitHub REST API. The response summarizes the repository without checking out or executing its files.

Example request:

```json
{
  "repository_url": "https://github.com/tiangolo/fastapi"
}
```

The response includes the repository name and description, default branch, languages, detected frameworks, manifest dependencies, test frameworks, conventional entry points, Docker-file presence, the manifests read, and the number of included source tree entries.

## Detection scope

- Languages come from GitHub's repository language endpoint.
- Dependency/framework detection currently reads selected `requirements.txt`, `pyproject.toml`, `package.json`, `Pipfile`, `Gemfile`, `go.mod`, `Cargo.toml`, and `composer.json` files.
- Test tooling detection recognizes pytest, Jest, Vitest, Playwright, Cypress, and the Django test runner.
- Entry points use common Python, JavaScript/TypeScript, and Go paths. This is a heuristic, not a claim that the file is the application's actual runtime entry point.
- Docker detection looks for `Dockerfile`, Docker Compose files, and Compose YAML names.

Analysis is bounded to eight manifests, each no larger than 64 KiB. Generated folders such as `node_modules`, `.venv`, `vendor`, `build`, and `dist` are excluded from the reported file count and heuristics. GitHub may return a truncated tree; the response reports that condition.

## Current limitations

- Public repositories on GitHub.com only; private repositories and GitHub Enterprise are not supported.
- GitHub's unauthenticated API rate limit applies. A 503 response indicates GitHub denied a request or the public rate limit was reached.
- A 404 means the repository is missing or not publicly accessible.
- Language totals and manifest parsing are best-effort signals. Unsupported dependency formats or unusual project layouts may not be detected.
- Orbit does not clone, install dependencies from, build, or run repository code in this milestone.
- API requests time out after eight seconds. Retrying is safe because analysis makes read-only requests.

## Safety boundary

The input URL is parsed into an owner and repository name before any request. Orbit only sends requests to the fixed `api.github.com` host, follows no redirects, fetches only known manifest paths from the repository tree, ignores symlinks, and never evaluates repository content as code. Future execution features need a separate isolated runner with resource, filesystem, network, and time limits before they can be enabled.

## Checkpoint for 0.1

The checkpoint passed with 15 backend tests, including URL validation, public repository success, missing repositories, GitHub rate limiting, safe redirect handling, and project metadata detection. Docker Compose rebuilt the API, and a live request for `https://github.com/tiangolo/fastapi` returned a report through the container. This verifies one public repository and the supported manifest heuristics; it does not prove detection for every project layout.
