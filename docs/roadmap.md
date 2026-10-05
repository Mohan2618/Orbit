# Orbit development roadmap

This roadmap adapts the supplied TestPilot product specification to the Orbit project name. The specification describes the product vision; this file records the current release sequence.

| Release | Focus | Completion checkpoint |
| --- | --- | --- |
| 0.0 | Foundation | API, health endpoint, tests, Docker Compose API/PostgreSQL/Redis, documentation |
| 0.1 | Repository intelligence | A repository URL produces a useful language, framework, dependency, and test-tool report |
| 0.2 | Basic QA engine | Existing checks run in an isolated environment and results are normalized into a report |
| 0.3 | AI test generation | Generated tests are reviewed, executed safely, and reported with evidence |
| 0.4–0.8 | API, UI, performance, security, and AI/ML QA | Each dimension has a working integration and its own checked milestone |
| 0.9 | Autonomous QA loop | Discovery, planning, execution, analysis, and retesting work end to end |
| 1.0 | Production platform | Dashboard, GitHub integration, CI workflows, scheduled runs, and team features |

## Current release: 0.0

Orbit 0.0 is a local foundation, not yet a QA runner. PostgreSQL and Redis are provisioned for upcoming milestones but are not connected to the API. The service accepts no repository uploads and executes no submitted code.

The 0.0 checkpoint is complete when the backend tests pass, the API works locally, and Docker Compose reports the API, PostgreSQL, and Redis healthy. The next release should not start while one of those checks is failing.
