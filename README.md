# Orbit

Orbit is a self-hosted QA orchestration platform for public GitHub repositories. It records asynchronous runs, downloads source archives without executing them on the API or worker host, performs a fixed Python test suite in disposable Docker sandboxes, and returns evidence in a web dashboard and JSON API.

## v1.0 release scope

- Repository discovery from GitHub metadata and bounded source inspection.
- Durable PostgreSQL run records and Redis/Celery asynchronous execution.
- Isolated Python pytest, Ruff, and coverage execution with resource limits.
- Static API-spec, UI accessibility, security-pattern, performance-footprint, and ML dataset checks.
- Candidate test-gap reporting based on Python syntax trees.
- Opt-in OpenAI test generation with candidate review and approval before sandbox execution.
- Classification and regression metrics for explicitly selected CSV/JSONL prediction columns.
- Recurring schedules, signed GitHub push webhooks, optional bearer API-key protection, and a dashboard.
- GitHub Actions workflows for Orbit CI and optional remote Orbit QA runs.

The non-Python API/UI/performance dimensions currently use bounded static checks. Orbit does not boot submitted applications, issue live HTTP traffic to them, or run browser automation. Static findings are leads for review, not proof of runtime vulnerabilities or performance. The ML evaluation endpoint calculates metrics only when the user supplies label and prediction columns. Python repository execution is available only through the sandboxed worker. See [the run security boundary](docs/qa-execution-security.md).

## Start the local platform

Install Docker Desktop, then from the repository root:

```powershell
Copy-Item .env.example .env
# Set POSTGRES_PASSWORD to a private local value before deployment.
docker compose up --build -d
docker compose ps
```

Open `http://127.0.0.1:8000/dashboard` for the dashboard, `/docs` for the API, `/health` for liveness, and `/ready` for PostgreSQL/Redis readiness. Compose starts PostgreSQL, Redis, database migrations, the API, one Celery worker, and Celery Beat.

To protect API routes, set `ORBIT_API_KEY` in `.env` and restart the API. Requests then need `Authorization: Bearer <key>`. This release uses one shared key for a self-hosted team; it does not provide per-user accounts or role-based access control. Set `GITHUB_WEBHOOK_SECRET` to the secret configured for a GitHub repository's push webhook. The GitHub Actions integration requires `ORBIT_API_URL` and `ORBIT_API_KEY` repository secrets.

Test generation is disabled until `OPENAI_API_KEY` and `ORBIT_TEST_GENERATION_MODEL` are set in `.env`. The API will send only the selected `.py` source file to OpenAI after the request explicitly sets `share_source_with_model=true`. Orbit redacts common literal secret patterns, asks the Responses API not to store the response, and returns the generated candidate for review. Approve a candidate with `POST /api/v1/generated-tests/{id}/approve`; then include its ID in a test-run request to execute it in the same restricted container as repository tests. Generated code remains untrusted. The source-sharing opt-in is required for every generation request.

The worker needs Docker Engine access to create isolated test containers. Keep it on a trusted development host or place it on a dedicated execution host. The Docker socket grants broad host control; the web API does not receive that socket. Configure strong secrets, TLS at the deployment ingress, backups, monitoring, and a dedicated runner host before exposing this single-team deployment to untrusted users.

## Use the API

Queue a run for a public GitHub repository:

```powershell
$headers = @{}
if ($env:ORBIT_API_KEY) { $headers.Authorization = "Bearer $env:ORBIT_API_KEY" }
$body = @{ repository_url = "https://github.com/tiangolo/fastapi" } | ConvertTo-Json
$run = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/test-runs -Headers $headers -ContentType "application/json" -Body $body
Invoke-RestMethod "http://127.0.0.1:8000/api/v1/test-runs/$($run.id)" -Headers $headers
```

Create a recurring run every 24 hours (minimum interval 15 minutes):

```powershell
$body = @{ repository_url = "https://github.com/tiangolo/fastapi"; interval_minutes = 1440 } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/schedules -Headers $headers -ContentType "application/json" -Body $body
```

The signed webhook endpoint is `/api/v1/integrations/github/webhook`. Configure GitHub to send `push` events as JSON and use the same `GITHUB_WEBHOOK_SECRET`. Duplicate delivery IDs are ignored.

Generate a candidate (source is shared with the configured model only because this request opts in):

```json
POST /api/v1/generated-tests
{
  "repository_url": "https://github.com/owner/repository",
  "source_path": "src/calculator.py",
  "share_source_with_model": true
}
```

Review the returned `test_code`, approve its ID, and pass `generated_test_id` when creating a run. For labeled prediction files, `POST /api/v1/ml-evaluations` accepts `repository_url`, `source_path`, `label_column`, `prediction_column`, and `task_type` (`classification` or `regression`). It reports accuracy/macro precision/recall/F1 or MAE/RMSE/R² with row limits and skipped-row counts.

## Develop locally

```powershell
python -m venv backend\.venv
.\backend\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements-dev.txt
python -m uvicorn app.main:app --app-dir backend --reload
```

Set `DATABASE_URL=sqlite:///./orbit.db` and `REDIS_URL=redis://localhost:6379/0` for local development. Database schema updates run through Alembic migrations; do not use `create_all` in production.

## Verify and release

The complete verification pass is intentionally run after the v1.0 implementation is assembled. From the root:

```powershell
python -m compileall -q backend/app backend/migrations
python -m pytest backend/tests -q
docker compose config --quiet
docker compose up --build -d
docker compose ps
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/ready
```

The CI workflow runs the backend checks and validates the Compose configuration. `.github/workflows/orbit-qa.yml` can run a scheduled or manually dispatched QA run when its API URL and key secrets are configured.

## Project documents

- [Development roadmap](docs/roadmap.md)
- [Repository intelligence](docs/repository-intelligence.md)
- [QA execution security boundary](docs/qa-execution-security.md)
