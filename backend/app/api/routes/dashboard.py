from html import escape
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.run_schedule import RunSchedule
from app.models.test_run import TestRun

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


@router.get("/summary")
def dashboard_summary(session: Session = Depends(get_db)) -> dict:
    counts = dict(session.execute(select(TestRun.status, func.count()).group_by(TestRun.status)).all())
    recent = session.scalars(select(TestRun).order_by(TestRun.created_at.desc()).limit(10)).all()
    return {
        "runs_by_status": counts,
        "total_runs": sum(counts.values()),
        "active_schedules": session.scalar(select(func.count()).select_from(RunSchedule)) or 0,
        "recent_runs": [
            {"id": run.id, "repository_url": run.repository_url, "status": run.status,
             "outcome": (run.result or {}).get("outcome"), "created_at": run.created_at,
             "completed_at": run.completed_at}
            for run in recent
        ],
    }


@router.get("/runs/{test_run_id}", response_class=HTMLResponse, include_in_schema=False)
def dashboard_run_detail(test_run_id: str, session: Session = Depends(get_db)) -> HTMLResponse:
    run = session.scalar(select(TestRun).where(TestRun.id == test_run_id))
    if run is None:
        raise HTTPException(status_code=404, detail="Test run not found.")

    result = run.result or {}
    steps = result.get("steps") or []
    counts = result.get("counts") or {}
    repo = result.get("repository") or {}
    dims = result.get("dimensions") or {}
    generation = dims.get("generation") or {}
    security = dims.get("security") or {}
    plan = result.get("qa_plan") or {}
    outcome = result.get("outcome") or run.error_message or "—"

    def status_class(value: str) -> str:
        if value in {"passed", "complete"}:
            return "good"
        if value in {"failed", "runner_failed", "timed_out"}:
            return "bad"
        return "warn"

    step_rows = "".join(
        f'<div class="step"><span class="step-name">{escape(str(step.get("name", "step")))}</b>'
        f'<span class="{status_class("passed" if step.get("return_code") == 0 else "failed")}">'
        f'{escape("Passed" if step.get("return_code") == 0 else ("Timed out" if step.get("timed_out") else "Exit " + str(step.get("return_code"))))}</span>'
        f'<small>{escape(str(step.get("duration_seconds", "—")))}s</small></div>'
        for step in steps
    ) or '<p>No execution steps recorded.</p>'

    candidates = generation.get("candidates") or []
    gap_rows = "".join(
        f'<div class="card"><b>{escape(str(item.get("source_file", "")))}</b>'
        f'<p>Missing tests: {escape(", ".join(item.get("functions_without_matching_test_file") or []))}</p>'
        f'<small>Suggested: {escape(str(item.get("suggested_test_file", "—")))}</small></div>'
        for item in candidates
    ) or '<p>No test gaps identified.</p>'

    raw = escape(json.dumps(run.result, indent=2, default=str))
    message = run.error_message or result.get("error_message")

    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Orbit QA Run</title>
<style>
body{{margin:0;background:#0a1014;color:#edf4f2;font:15px system-ui,sans-serif}}
main{{max-width:1100px;margin:0 auto;padding:42px 24px 80px}}
a{{color:#9be6c1}} .eyebrow{{color:#9be6c1;font:11px monospace;letter-spacing:.14em}}
.panel{{background:#111a20;border:1px solid #223039;border-radius:13px;padding:22px;margin:14px 0}}
.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}}
.card{{background:#0d151a;border:1px solid #223039;border-radius:9px;padding:16px;margin:8px 0}}
.card span,.step span{{display:block;color:#9be6c1;margin-top:7px}} .good{{color:#9be6c1!important}} .bad{{color:#ff8f8f!important}} .warn{{color:#ffcf8a!important}}
.step{{display:grid;grid-template-columns:1fr auto auto;gap:20px;padding:12px 0;border-bottom:1px solid #223039}}
small,p{{color:#9aaeb0;line-height:1.6}} pre{{white-space:pre-wrap;overflow:auto;background:#080d10;padding:16px;border-radius:8px}}
@media(max-width:700px){{.grid{{grid-template-columns:repeat(2,1fr)}}.step{{grid-template-columns:1fr}}}}
</style></head><body><main>
<p class="eyebrow">ORBIT · RUN DETAILS</p>
<div class="hero"><div><h1>QA run {escape(str(run.id)[:8])}…</h1>
<a class="back-link" href="/dashboard">← Back to dashboard</a>
<div class="panel"><p class="repo">{escape(run.repository_url)}</p></div><span class="outcome-badge {status_class(str(outcome))}">{escape(str(outcome))}</span></div>
<div class="panel"><div class="summary-grid">
<div class="card"><small>Status</small><b>{escape(run.status)}</b></div>
<div class="card"><small>Outcome</small><b class="{status_class(str(outcome))}">{escape(str(outcome))}</b></div>
<div class="card"><small>Passed</small><b>{escape(str(counts.get("passed", 0)))}</b></div>
<div class="card"><small>Failed</small><b>{escape(str(counts.get("failed", 0)))}</b></div>
<div class="card"><small>Coverage</small><b>{escape(str(result.get("coverage_percent", "—")))}%</b></div>
<div class="card"><small>Duration</small><b>{escape(str(result.get("duration_seconds", "—")))}s</b></div>
</div></div>
<div class="panel"><div class="section-head"><h2>Execution</h2><small>{len(steps)} steps</small></div><div class="step-list">{step_rows}</div></div>
<div class="panel"><div class="section-head"><h2>Repository analysis</h2><small>Static inspection</small></div><p><b>{escape(str(repo.get("full_name", run.repository_url)))}</b> · {escape(", ".join(repo.get("languages") or []) or "Unknown")} · {escape(str(repo.get("analyzed_files", 0)))} files analyzed</p></div>
<div class="panel"><div class="section-head"><h2>Test gaps</h2><small>{len(candidates)} candidate(s)</small></div>{gap_rows}</div>
<div class="analysis-grid">
<div class="info-card"><b>Security</b><span class="value">{escape(str(security.get("finding_count", 0)))} findings</span></div>
<div class="info-card"><b>Generation candidates</b><span class="value">{escape(str(generation.get("count", 0)))}</span></div>
<div class="info-card"><b>QA checks</b><span class="value">{escape(str(len(plan.get("selected_checks") or [])))}</span></div>
</div>
{f'<div class="panel message"><strong>Run message</strong><p>{escape(str(message))}</p></div>' if message else ''}
<div class="panel"><details><summary>Raw result JSON</summary><pre>{raw}</pre></details></div>
</main></body></html>"""
    return HTMLResponse(html)
