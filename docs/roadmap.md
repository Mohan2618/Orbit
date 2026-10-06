# Orbit release roadmap

This roadmap tracks the supplied TestPilot specification under the Orbit project name. Version 1.0 is being assembled before the full test and runtime verification pass.

| Release | Scope | Current state |
| --- | --- | --- |
| 0.0 | FastAPI service, health checks, Docker Compose, docs | Previously completed and locally verified |
| 0.1 | Read-only GitHub repository intelligence | Previously completed and live-checked on a public repository |
| 0.2 | Persisted asynchronous Python QA runs in restricted Docker containers | Implemented; final regression and Compose verification pending |
| 0.3 | Model-assisted test candidates, explicit source-sharing consent, review, approval, sandbox execution | Implemented; provider-backed integration verification requires configured OpenAI credentials |
| 0.4 | API QA | Static OpenAPI/Swagger discovery and JSON structural checks; live endpoint contract traffic is not enabled |
| 0.5 | UI QA | Static HTML accessibility signals; browser-based interaction is not enabled |
| 0.6 | Performance QA | Repository/file footprint measurements; runtime load benchmarking is not enabled |
| 0.7 | Security QA | Bounded source pattern scan for triage; not a penetration test |
| 0.8 | AI/ML evaluation | Explicit CSV/JSONL classification and regression evaluation endpoint |
| 0.9 | Autonomous QA loop | Rule-based check selection, async execution, evidence report, and human-approved generated-test reruns |
| 1.0 | Platform | Dashboard, API key, signed GitHub push webhook, CI workflows, recurring schedules, PostgreSQL/Redis/Celery, Alembic migrations |

## 1.0 release gate

Do not publish the v1.0 branch until the final integrated pass succeeds:

1. Compile the backend and migration modules.
2. Run the complete backend unit/API test suite, including test generation safety, ML metrics, schedules, webhooks, and the sandbox orchestration boundary.
3. Validate the Compose configuration, build all services, apply migrations, and confirm API/PostgreSQL/Redis/worker/beat health.
4. Exercise API health/readiness, repository analysis, one public Python QA run, dashboard loading, schedule create/delete, API-key rejection/acceptance, and webhook signature/idempotency.
5. Inspect all run evidence, deployment notes, working tree, and GitHub remote before requesting the user's go-ahead to publish.

The final gate has not yet been run. The current local Compose stack may still reflect the older image until rebuilt from this worktree. CI will run after the implementation is assembled, not as a substitute for runtime checks.

## Explicit v1.0 limits

The executable run supports public GitHub Python repositories, PyPI binary wheels, pytest, Ruff, and coverage. API/UI/performance checks inspect repository artifacts without starting user applications. Model generation is an optional external provider call that requires an explicit source-sharing flag; generated tests need human approval. Teams use one shared API key; there are no per-user accounts or role assignments. Production deployment still needs an isolated remote runner host, a TLS ingress, configured secrets, monitoring, backups, and operational policies.
