"""Trusted command wrapper invoked inside a disposable, networkless test container."""

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

MAX_LOG_BYTES = 1024 * 1024


def run_step(
    name: str,
    command: list[str],
    timeout: int,
    log_path: Path,
    *,
    env: dict[str, str] | None = None,
) -> dict:
    started = time.monotonic()
    with log_path.open("wb") as log_file:
        try:
            completed = subprocess.run(
                command,
                cwd="/tmp",
                env=env or os.environ.copy(),
                stdout=log_file,
                stderr=subprocess.STDOUT,
                timeout=timeout,
                check=False,
            )
            return {
                "name": name,
                "return_code": completed.returncode,
                "duration_seconds": round(time.monotonic() - started, 3),
                "timed_out": False,
            }
        except subprocess.TimeoutExpired:
            return {
                "name": name,
                "return_code": None,
                "duration_seconds": round(time.monotonic() - started, 3),
                "timed_out": True,
            }


def tail(path: Path) -> str:
    with path.open("rb") as output_file:
        output_file.seek(0, os.SEEK_END)
        size = output_file.tell()
        output_file.seek(max(0, size - MAX_LOG_BYTES))
        return output_file.read(MAX_LOG_BYTES).decode("utf-8", errors="replace")


def main() -> int:
    packages = json.loads(os.getenv("ORBIT_PACKAGES", "[]"))
    if not isinstance(packages, list) or any(
        not isinstance(name, str)
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}", name)
        for name in packages
    ):
        print(json.dumps({"outcome": "failed", "error_message": "Invalid dependency list."}))
        return 2

    os.environ.update(
        {
            "HOME": "/tmp",
            "PIP_CONFIG_FILE": "/dev/null",
            "PIP_NO_INDEX": "1",
            "PIP_NO_CACHE_DIR": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTEST_ADDOPTS": "-p no:cacheprovider",
            "PYTHONPATH": "/tmp/orbit-packages:/workspace",
        }
    )
    log_directory = Path("/tmp/orbit-logs")
    log_directory.mkdir(mode=0o700)
    steps: list[dict] = []
    resolved_dependencies: list[dict] = []

    if packages:
        install = run_step(
            "install_dependencies",
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--no-index",
                "--no-cache-dir",
                "--disable-pip-version-check",
                "--find-links=/wheelhouse",
                "--target=/tmp/orbit-packages",
                "--report=/tmp/pip-report.json",
                *packages,
            ],
            timeout=120,
            log_path=log_directory / "install.log",
            env={
                **os.environ,
                "PYTHONPATH": "/tmp/orbit-packages",
            },
        )
        steps.append(install)
        if install["timed_out"] or install["return_code"] != 0:
            report = {
                "outcome": "dependency_install_failed",
                "steps": steps,
                "error_message": "The dependencies could not be installed from binary wheels within the isolated runner.",
                "output": tail(log_directory / "install.log"),
            }
            print(json.dumps(report))
            return 1
        with Path("/tmp/pip-report.json").open(encoding="utf-8") as report_file:
            pip_report = json.load(report_file)
        resolved_dependencies = [
            {
                "name": item.get("metadata", {}).get("name"),
                "version": item.get("metadata", {}).get("version"),
            }
            for item in pip_report.get("install", [])
            if isinstance(item, dict) and isinstance(item.get("metadata"), dict)
        ]

    # /tmp is mounted noexec in the sandbox, so the generated console script
    # cannot be executed directly. Invoke Ruff through the Python interpreter.
    ruff = run_step(
        "ruff",
        [sys.executable, "-m", "ruff", "check", "--output-format=json", "/workspace"],
        timeout=45,
        log_path=log_directory / "ruff.log",
        env={**os.environ, "PYTHONPATH": "/tmp/orbit-packages"},
    )
    ruff_output = tail(log_directory / "ruff.log")
    try:
        raw_findings = json.loads(ruff_output)
    except json.JSONDecodeError:
        raw_findings = []
    findings = [
        {
            "code": item.get("code"),
            "message": item.get("message"),
            "filename": item.get("filename"),
            "line": item.get("location", {}).get("row"),
            "column": item.get("location", {}).get("column"),
        }
        for item in raw_findings[:1000]
        if isinstance(item, dict)
    ] if isinstance(raw_findings, list) else []

    pytest = run_step(
        "pytest",
        [
            sys.executable,
            "/app/app/execution/run_pytest.py",
            "--cov=/workspace",
            "--cov-report=json:/tmp/coverage.json",
        ],
        timeout=240,
        log_path=log_directory / "pytest.log",
        env={**os.environ, "PYTHONPATH": "/tmp/orbit-packages"},
    )
    steps.append(pytest)
    output = tail(log_directory / "pytest.log")
    coverage_percent = None
    coverage_path = Path("/tmp/coverage.json")
    if coverage_path.is_file():
        try:
            coverage_data = json.loads(coverage_path.read_text(encoding="utf-8"))
            coverage_percent = coverage_data.get("totals", {}).get("percent_covered")
        except (OSError, json.JSONDecodeError):
            pass
    counts = {
        label: int(count)
        for count, label in re.findall(
            r"\b(\d+)\s+(passed|failed|error|skipped|xfailed|xpassed|deselected)\b", output
        )
    }
    if pytest["timed_out"]:
        outcome = "timed_out"
        error_message = "The pytest run exceeded the four-minute execution limit."
    elif pytest["return_code"] == 5:
        outcome = "no_tests_found"
        error_message = "Pytest did not find any tests in the repository."
    elif pytest["return_code"] != 0:
        outcome = "failed"
        error_message = None
    elif ruff["timed_out"] or ruff["return_code"] != 0:
        outcome = "failed"
        error_message = "The Ruff static-analysis check reported findings or did not complete."
    else:
        outcome = "passed"
        error_message = None

    print(
        json.dumps(
            {
                "outcome": outcome,
                "steps": steps,
                "counts": counts,
                "resolved_dependencies": resolved_dependencies,
                "static_analysis": {
                    "tool": "ruff",
                    "return_code": ruff["return_code"],
                    "timed_out": ruff["timed_out"],
                    "findings_count": len(findings),
                    "findings": findings,
                    "output": ruff_output if ruff["return_code"] not in {0, 1} else None,
                },
                "coverage_percent": coverage_percent,
                "error_message": error_message,
                "output": output,
            }
        )
    )
    return 0 if outcome == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
