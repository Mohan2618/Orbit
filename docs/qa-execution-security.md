# QA execution and data boundaries

Orbit 1.0 is a self-hosted single-team QA platform. It accepts public GitHub repositories, stores run records in PostgreSQL, and uses Redis/Celery for asynchronous work. API key protection is optional for local development; configure `ORBIT_API_KEY` before exposing API routes. The key is shared by the team and does not provide per-user roles.

## Python repository run path

1. The API validates a `github.com/owner/repository` URL, persists the run, and enqueues its ID.
2. The trusted worker calls GitHub's API and downloads the public repository archive into temporary disk space.
3. Extraction rejects traversal, ignores links and special files, and enforces compressed-size, expanded-size, file-count, and entry-count limits.
4. The worker derives plain Python package names from recognized manifests. A separate downloader container can fetch binary wheels from the fixed PyPI index. It receives no repository source and builds no source distributions.
5. The runner installs the downloaded wheels offline and executes pytest, Ruff, and coverage in a disposable container. An approved generated test is added to the temporary source tree before it is mounted read-only.
6. The result records test counts, coverage, static QA dimensions, generated-test provenance, dependency versions, timings, and bounded logs.

## Sandbox limits

- Network mode `none` for installation and test execution; the dependency downloader is network-enabled only to reach the fixed PyPI index.
- Read-only root filesystem and read-only source/wheel mounts in test execution.
- Non-root UID, all Linux capabilities dropped, and `no-new-privileges`.
- Memory, CPU, process-count, wall-clock, archive-size, and captured-output limits.
- A small writable `/tmp`; no host directories, database credentials, Redis credentials, or Docker socket enter the test container.
- Containers and named volumes are removed after the run.

Only the Celery worker has Docker Engine access. A Docker socket grants broad host control; therefore the Compose stack is for a trusted development machine. A public deployment should put the worker on a dedicated execution host with a separate Docker daemon or remote runner service, restrict ingress and egress, configure TLS, rotate secrets, and back up PostgreSQL. The API service itself does not mount the Docker socket.

## Generated test source sharing

Test generation is disabled unless `OPENAI_API_KEY` and `ORBIT_TEST_GENERATION_MODEL` are configured. Each request must set `share_source_with_model=true`; it sends one selected Python file (maximum 24,000 characters) to the OpenAI Responses API. Common literal credential patterns are redacted and response storage is disabled in the request. This is best-effort redaction, not a guarantee that source contains no secrets. Review candidate code before calling the approval endpoint. Approved code still runs as untrusted input in the sandbox. The AST review rejects selected imports and calls, but it is not a security proof; the sandbox is the execution boundary.

## Other QA dimensions

API specification, UI/accessibility, security-pattern, and performance-footprint checks inspect bounded repository files without starting the submitted app or making requests to it. Their results are static signals and may be incomplete or produce false positives. The ML evaluator parses a user-selected CSV/JSONL artifact up to 2 MiB and 10,000 rows; the caller explicitly maps label and prediction columns. It computes standard exact-label classification metrics or numeric regression metrics, but does not assess dataset quality or statistical significance.

## Current support limits

- Public repositories on GitHub.com only; private repositories and GitHub Enterprise are unsupported.
- The executable test runner supports Python and pytest. Non-Python code gets static reports but is not executed.
- Dependencies must be available as binary wheels on PyPI. Custom build scripts, repository Dockerfiles, install hooks, application startup, custom test commands, and network access from tests are not supported.
- Live API contract checks, browser automation, and load generation need an isolated target-runtime service and are not part of this release's static checks.
- The single shared API key has no user/team role model. Generation endpoints should be protected by that key in any reachable deployment because model calls may incur cost.
