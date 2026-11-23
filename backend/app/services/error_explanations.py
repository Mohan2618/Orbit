"""Deterministic, user-facing explanations of isolated QA execution results."""

import re

RUFF_GUIDANCE = {
    "F401": ("Unused import", "This import is not used by the file.", "Remove the unused import, or use it where needed."),
    "F821": ("Undefined name", "Code refers to a name Python cannot find.", "Check spelling and define or import the name."),
    "E501": ("Line too long", "A line exceeds the configured length limit.", "Break the expression into shorter lines."),
    "F841": ("Unused variable", "A local variable is assigned but never used.", "Remove the assignment or use the variable."),
}


def explain_result(result: dict) -> list[dict[str, str]]:
    """Return actionable findings without inventing file locations or causes."""
    explanations: list[dict[str, str]] = []
    steps = {step.get("name"): step for step in result.get("steps", []) if isinstance(step, dict)}
    analysis = result.get("static_analysis") or {}

    for finding in analysis.get("findings") or []:
        if not isinstance(finding, dict):
            continue
        code = str(finding.get("code") or "Ruff")
        title, cause, fix = RUFF_GUIDANCE.get(
            code, ("Ruff code-quality finding", str(finding.get("message") or "Ruff flagged this code."),
                   "Review the rule and update the indicated code, then rerun QA.")
        )
        location = str(finding.get("filename") or "")
        if finding.get("line") is not None:
            location += f":{finding['line']}"
        explanations.append({
            "category": "repository", "severity": "warning", "tool": "ruff",
            "title": f"{code}: {title}", "cause": cause, "fix": fix,
            "location": location, "evidence": str(finding.get("message") or ""),
        })

    ruff = steps.get("ruff") or {}
    if ruff.get("timed_out"):
        explanations.append({
            "category": "execution", "severity": "error", "tool": "ruff",
            "title": "Ruff timed out", "cause": "Static analysis exceeded the configured time limit.",
            "fix": "Retry the analysis. If it repeats, check repository size and Orbit runner limits.",
            "location": "", "evidence": "",
        })
    elif ruff.get("return_code") not in (None, 0, 1) or (
        ruff.get("return_code") == 1 and not analysis.get("findings")
    ):
        raw = str(analysis.get("output") or "")
        cache_failure = "Failed to initialize cache" in raw or "Read-only file system" in raw
        explanations.append({
            "category": "infrastructure" if cache_failure else "execution",
            "severity": "error", "tool": "ruff",
            "title": "Ruff runner could not complete" if not cache_failure else "Ruff cache write failed",
            "cause": ("Ruff attempted to write to a read-only sandbox."
                      if cache_failure else "Ruff exited without usable lint findings."),
            "fix": ("Orbit maintainers should run Ruff with --no-cache."
                    if cache_failure else "Inspect the raw Ruff output and runner configuration; retry the run."),
            "location": "", "evidence": raw[:500],
        })

    install = steps.get("install_dependencies") or {}
    if install.get("timed_out") or install.get("return_code") not in (None, 0):
        explanations.append({
            "category": "environment", "severity": "error", "tool": "dependencies",
            "title": "Dependency installation failed",
            "cause": "Required packages could not be installed in the isolated environment.",
            "fix": "Check package names, compatible versions and available binary wheels.",
            "location": "", "evidence": str(result.get("error_message") or ""),
        })

    pytest = steps.get("pytest") or {}
    if pytest.get("timed_out"):
        explanations.append({
            "category": "execution", "severity": "error", "tool": "pytest",
            "title": "Tests exceeded the time limit",
            "cause": "Pytest did not finish before Orbit's configured timeout.",
            "fix": "Check for hanging tests, long waits or expensive setup, then rerun.",
            "location": "", "evidence": "",
        })
    elif pytest.get("return_code") == 5 or result.get("outcome") == "no_tests_found":
        explanations.append({
            "category": "repository", "severity": "warning", "tool": "pytest",
            "title": "No tests discovered",
            "cause": "Pytest did not find tests matching its discovery rules.",
            "fix": "Check test file names (for example test_example.py), test paths and pytest configuration.",
            "location": "", "evidence": "",
        })
    elif pytest.get("return_code") not in (None, 0):
        output = str(result.get("output") or "")
        match = re.search(r"(?m)^FAILED\s+([^\s]+)", output)
        explanations.append({
            "category": "repository" if pytest.get("return_code") == 1 else "execution",
            "severity": "error", "tool": "pytest",
            "title": "Tests failed" if pytest.get("return_code") == 1 else "Pytest could not complete",
            "cause": ("One or more test assertions failed." if pytest.get("return_code") == 1
                      else "Pytest reported an execution or collection error."),
            "fix": "Inspect the failure traceback in raw logs, fix the underlying issue and rerun.",
            "location": match.group(1) if match else "", "evidence": "",
        })
    return explanations
