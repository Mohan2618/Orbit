# Orbit

Orbit is an autonomous software QA platform. It will inspect software projects, choose relevant checks, orchestrate established testing tools, and turn their results into traceable findings.

The project is being built in small releases. The current foundation release (`0.0.1`) provides a documented FastAPI service, a health endpoint, a test suite, and a local Docker Compose environment. Repository analysis and test execution are later milestones.

## Run the API locally

From the repository root, create and activate the backend virtual environment:

```powershell
py -m venv backend\.venv
.\backend\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements-dev.txt
python -m uvicorn app.main:app --app-dir backend --reload
```

Open `http://127.0.0.1:8000/health` for the health response and `http://127.0.0.1:8000/docs` for Swagger UI.

## Run the foundation checks

From the repository root:

```powershell
python -m pytest backend\tests -q
```

## Run with Docker Compose

Install Docker Desktop, then run from the repository root:

```powershell
Copy-Item .env.example .env
docker compose up --build -d
docker compose ps
Invoke-RestMethod http://127.0.0.1:8000/health
```

Compose starts the API, PostgreSQL, and Redis with readiness checks. In this release the API does not yet store data in PostgreSQL or enqueue work in Redis. Local Compose credentials are for development only; replace them before using this setup outside a private development machine.

Stop the services with `docker compose down`. To also delete the local PostgreSQL data volume, use `docker compose down --volumes`.

## Development roadmap

1. **0.0 — Foundation:** API, local services, and a repeatable checkpoint.
2. **0.1 — Repository intelligence:** inspect a GitHub repository and report its language, framework, dependencies, and test tooling.
3. **0.2 — Basic QA engine:** run selected checks in a restricted environment and report results.
4. **0.3 onward:** generated tests, API, UI, performance, security, and AI/ML evaluation.

The product specification is the architectural reference; each milestone should be completed and checked before the next begins. Orbit must not run submitted code directly on the API host.
