"""Bounded, static QA checks that never import or execute repository code."""

from __future__ import annotations

import ast
import csv
import json
from pathlib import Path
import re

MAX_SOURCE_FILES = 2_000
MAX_SOURCE_BYTES = 2 * 1024 * 1024
MAX_FILE_BYTES = 256 * 1024


def inspect_repository(root: Path) -> dict:
    """Collect deterministic QA signals from a downloaded source tree."""
    files = []
    total_bytes = 0
    for path in root.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(root).as_posix()
        if any(part in {".git", "node_modules", ".venv", "vendor", "dist", "build"} for part in relative.split("/")):
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size > MAX_FILE_BYTES or total_bytes + size > MAX_SOURCE_BYTES:
            continue
        files.append((path, relative, size))
        total_bytes += size
        if len(files) >= MAX_SOURCE_FILES:
            break

    return {
        "api": _api_spec_checks(files),
        "security": _security_checks(files),
        "performance": _performance_signals(files),
        "ui": _ui_checks(files),
        "ml": _ml_evaluation(files),
        "generation": _test_generation_candidates(files),
    }


def _text(path: Path, size: int) -> str | None:
    if size > MAX_FILE_BYTES:
        return None
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _api_spec_checks(files: list[tuple[Path, str, int]]) -> dict:
    specs = []
    for path, relative, size in files:
        lowered = relative.lower()
        if not (lowered.endswith("openapi.json") or lowered.endswith("openapi.yaml") or lowered.endswith("openapi.yml") or lowered.endswith("swagger.json")):
            continue
        content = _text(path, size)
        if content is None:
            continue
        try:
            data = json.loads(content) if lowered.endswith(".json") else None
        except json.JSONDecodeError as exc:
            specs.append({"file": relative, "valid_json": False, "error": f"Invalid JSON near byte {exc.pos}"})
            continue
        if data is not None:
            specs.append({
                "file": relative,
                "valid_json": isinstance(data, dict),
                "openapi_version": data.get("openapi") if isinstance(data, dict) else None,
                "path_count": len(data.get("paths", {})) if isinstance(data, dict) and isinstance(data.get("paths"), dict) else 0,
                "has_info": isinstance(data, dict) and isinstance(data.get("info"), dict),
            })
        else:
            specs.append({"file": relative, "detected": True, "validation": "YAML parsing is not enabled in the static profile."})
    return {"status": "analyzed", "specifications": specs, "count": len(specs)}


def _security_checks(files: list[tuple[Path, str, int]]) -> dict:
    rules = [
        ("hardcoded_secret", re.compile(r"(?i)(api[_-]?key|secret|password|token)\s*[:=]\s*['\"][A-Za-z0-9_./+=-]{12,}['\"]")),
        ("unsafe_yaml_load", re.compile(r"yaml\.load\s*\(")),
        ("disabled_tls_verification", re.compile(r"verify\s*=\s*False")),
        ("subprocess_shell", re.compile(r"subprocess\.(?:run|Popen|call)\([^\n]{0,200}shell\s*=\s*True")),
    ]
    findings = []
    scanned = 0
    for path, relative, size in files:
        if path.suffix.lower() not in {".py", ".js", ".ts", ".jsx", ".tsx", ".yml", ".yaml", ".json", ".env", ".go", ".rb"}:
            continue
        content = _text(path, size)
        if content is None:
            continue
        scanned += 1
        for line_no, line in enumerate(content.splitlines(), 1):
            for rule, pattern in rules:
                if pattern.search(line):
                    findings.append({"rule": rule, "file": relative, "line": line_no, "severity": "medium"})
                    if len(findings) >= 500:
                        break
            if len(findings) >= 500:
                break
    return {"status": "static_scan", "files_scanned": scanned, "findings": findings, "finding_count": len(findings), "limitations": "Pattern matches are triage signals and may be false positives; this is not a penetration test."}


def _performance_signals(files: list[tuple[Path, str, int]]) -> dict:
    total = sum(size for _, _, size in files)
    large = [{"file": rel, "bytes": size} for _, rel, size in files if size >= 1_000_000][:100]
    return {"status": "static_profile", "files_scanned": len(files), "source_bytes_scanned": total, "large_files": large, "runtime_benchmark": "not_run; application startup and network load are not enabled in the safe repository profile"}


def _ui_checks(files: list[tuple[Path, str, int]]) -> dict:
    assets = [rel for _, rel, _ in files if Path(rel).suffix.lower() in {".html", ".css", ".js", ".jsx", ".tsx", ".vue", ".svelte"}]
    html_files = [(p, rel, size) for p, rel, size in files if Path(rel).suffix.lower() in {".html", ".htm"}]
    findings = []
    for path, relative, size in html_files[:100]:
        text = _text(path, size) or ""
        if "<title" not in text.lower():
            findings.append({"file": relative, "rule": "missing_document_title", "severity": "low"})
        if "<html" in text.lower() and "lang=" not in text.lower():
            findings.append({"file": relative, "rule": "missing_document_language", "severity": "low"})
    return {"status": "static_accessibility_scan", "ui_asset_count": len(assets), "html_file_count": len(html_files), "findings": findings, "browser_execution": "not_run; no app server is started by this profile"}


def _test_generation_candidates(files: list[tuple[Path, str, int]]) -> dict:
    candidates = []
    test_paths = {rel.lower() for _, rel, _ in files if "test" in Path(rel).name.lower() or "spec" in Path(rel).name.lower()}
    for path, relative, size in files:
        if path.suffix != ".py" or "test" in path.name.lower() or "spec" in path.name.lower():
            continue
        content = _text(path, size)
        if content is None:
            continue
        try:
            tree = ast.parse(content)
        except SyntaxError:
            continue
        public_functions = [node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_")]
        missing = [name for name in public_functions if not any(Path(test).stem.endswith(path.stem) for test in test_paths)]
        if missing:
            candidates.append({"source_file": relative, "functions_without_matching_test_file": missing[:50], "suggested_test_file": f"tests/test_{path.stem}.py"})
        if len(candidates) >= 200:
            break
    return {"status": "candidate_analysis", "candidates": candidates, "count": len(candidates), "generated_code": False, "note": "Review candidates before generating tests; source code is never submitted to an external model."}


def _ml_evaluation(files: list[tuple[Path, str, int]]) -> dict:
    datasets = []
    for path, relative, size in files:
        if path.suffix.lower() not in {".csv", ".jsonl"} or not any(term in relative.lower() for term in ("eval", "prediction", "label", "metric", "dataset")):
            continue
        content = _text(path, size)
        if content is None:
            continue
        try:
            if path.suffix.lower() == ".csv":
                rows = list(csv.DictReader(content.splitlines()))[:10_001]
                keys = list(rows[0]) if rows else []
            else:
                rows = [json.loads(line) for line in content.splitlines()[:10_000] if line.strip()]
                keys = sorted({key for row in rows if isinstance(row, dict) for key in row})
            datasets.append({"file": relative, "sample_rows": len(rows), "columns": keys[:100], "evaluation": "schema_only"})
        except (csv.Error, json.JSONDecodeError):
            datasets.append({"file": relative, "evaluation": "invalid_or_unsupported"})
    return {"status": "dataset_discovery", "datasets": datasets, "count": len(datasets), "metrics": "not computed; label and prediction columns require explicit configuration"}
