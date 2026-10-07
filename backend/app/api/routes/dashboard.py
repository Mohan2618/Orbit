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
:root{{--bg:#081014;--panel:#101a20;--panel2:#0c1419;--line:#23343d;--text:#edf5f2;--muted:#8fa5a7;--good:#8ee7bb;--bad:#ff8b8b;--warn:#ffd08a;--accent:#9be6c1}}
*{{box-sizing:border-box}} body{{margin:0;background:radial-gradient(circle at 85% -10%,#18352d 0,transparent 32%),var(--bg);color:var(--text);font:15px system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
main{{max-width:1120px;margin:0 auto;padding:34px 24px 80px}} a{{color:var(--accent)}} .back-link{{display:inline-flex;margin-bottom:22px;text-decoration:none}} .back-link:hover{{text-decoration:underline}}
.hero{{display:flex;justify-content:space-between;align-items:flex-end;gap:24px;margin-bottom:18px}} .eyebrow{{color:var(--accent);font:11px monospace;letter-spacing:.14em;margin:0 0 10px}} h1{{font-size:clamp(30px,5vw,46px);letter-spacing:-.04em;margin:0 0 8px}} h2{{font-size:20px;margin:0}} p,small{{color:var(--muted);line-height:1.65}} .repo{{word-break:break-all;margin:0}}
.outcome-badge{{padding:9px 13px;border-radius:999px;font:700 11px monospace;text-transform:uppercase;letter-spacing:.05em;border:1px solid currentColor;white-space:nowrap}} .good{{color:var(--good)!important}} .bad{{color:var(--bad)!important}} .warn{{color:var(--warn)!important}} .neutral{{color:#b7c5c3!important}}
.panel{{background:linear-gradient(145deg,var(--panel),#0d161b);border:1px solid var(--line);border-radius:16px;padding:24px;margin-top:14px;box-shadow:0 10px 30px #0002}}
.summary-grid{{display:grid;grid-template-columns:repeat(6,1fr);gap:10px}} .metric{{background:var(--panel2);border:1px solid var(--line);border-radius:11px;padding:15px}} .metric label{{display:block;color:var(--muted);font-size:11px;margin-bottom:7px}} .metric strong{{font-size:20px}}
.section-head{{display:flex;justify-content:space-between;align-items:center;gap:16px;margin-bottom:14px}} .step-list{{border:1px solid var(--line);border-radius:11px;overflow:hidden}} .step{{display:grid;grid-template-columns:1fr 90px 70px;gap:16px;align-items:center;padding:14px 16px;background:var(--panel2);border-bottom:1px solid var(--line)}} .step:last-child{{border-bottom:0}} .step-name{{font-weight:700}} .step-status{{text-align:center;font:700 11px monospace}} .step-time{{text-align:right}}
.analysis-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}} .info-card{{background:var(--panel2);border:1px solid var(--line);border-radius:11px;padding:17px}} .info-card .value{{display:block;font-size:20px;font-weight:700;margin-top:6px}}
.gap-card{{background:var(--panel2);border:1px solid var(--line);border-left:3px solid var(--warn);border-radius:11px;padding:17px}} .gap-card strong{{font-size:15px}} .code-list{{display:flex;flex-wrap:wrap;gap:7px;margin:12px 0}} .code-list span{{padding:5px 8px;border:1px solid var(--line);border-radius:7px;color:#d5e0dd;background:#101b20;font:12px monospace}}
.message{{border-color:#55482f;background:#17150f}} .message strong{{color:var(--warn)}} details summary{{cursor:pointer;color:var(--accent);font-weight:700}} pre{{white-space:pre-wrap;overflow:auto;max-height:520px;background:#070c0f;border:1px solid var(--line);padding:16px;border-radius:10px;font-size:12px;line-height:1.55}} .empty{{color:var(--muted);padding:8px 0}}
@media(max-width:900px){{.summary-grid{{grid-template-columns:repeat(3,1fr)}}.hero{{align-items:flex-start;flex-direction:column}}}}
@media(max-width:600px){{main{{padding:24px 14px 60px}}.summary-grid,.analysis-grid{{grid-template-columns:1fr 1fr}}.step{{grid-template-columns:1fr auto}}.step-time{{display:none}}}}
</style></head><body><main>
<p class="eyebrow">ORBIT · RUN DETAILS</p>
<a class="back-link" href="/dashboard">← Back to dashboard</a>
<div class="hero"><div><h1>QA run {escape(str(run.id)[:8])}…</h1><p class="repo">{escape(run.repository_url)}</p></div><span class="outcome-badge {status_class(str(outcome))}">{escape(str(outcome))}</span></div>

<div class="panel"><div class="summary-grid">
<div class="metric"><label>Status</label><strong>{escape(run.status)}</strong></div>
<div class="metric"><label>Outcome</label><strong class="{status_class(str(outcome))}">{escape(str(outcome))}</strong></div>
<div class="metric"><label>Passed</label><strong class="good">{escape(str(counts.get("passed", 0)))}</strong></div>
<div class="metric"><label>Failed</label><strong class="bad">{escape(str(counts.get("failed", 0)))}</strong></div>
<div class="metric"><label>Coverage</label><strong>{escape(str(result.get("coverage_percent", "—")))}%</strong></div>
<div class="metric"><label>Duration</label><strong>{escape(str(result.get("duration_seconds", "—")))}s</strong></div>
</div></div>

<div class="panel"><div class="section-head"><h2>Execution</h2><small>{len(steps)} step(s)</small></div><div class="step-list">{step_rows}</div></div>
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
