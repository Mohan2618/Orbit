"""Bounded, static QA checks that never import or execute repository code."""

from __future__ import annotations

import ast
import csv
import json
import re
from pathlib import Path

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
        if not lowered.endswith(
            ("openapi.json", "openapi.yaml", "openapi.yml", "swagger.json")
        ):
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
    """Inspect executable Python AST nodes instead of matching example strings."""
    findings: list[dict] = []
    scanned = 0
    for path, relative, size in files:
        if path.suffix.lower() != ".py":
            continue
        content = _text(path, size)
        if content is None:
            continue
        scanned += 1
        try:
            tree = ast.parse(content)
        except SyntaxError:
            continue
        imports = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports[alias.asname or alias.name] = alias.name
            elif isinstance(node, ast.ImportFrom) and node.module:
                for alias in node.names:
                    imports[alias.asname or alias.name] = node.module + "." + alias.name

        def resolved_name(node: ast.AST) -> str:
            if isinstance(node, ast.Name):
                return imports.get(node.id, node.id)
            if isinstance(node, ast.Attribute):
                return resolved_name(node.value) + "." + node.attr
            return ""

        is_test = any(part in {"tests", "test"} for part in Path(relative).parts) or path.name.startswith("test_")
        for node in ast.walk(tree):
            rule = None
            if isinstance(node, ast.Call):
                name = resolved_name(node.func)
                keywords = {kw.arg: kw.value for kw in node.keywords if kw.arg}
                if name in {"subprocess.run", "subprocess.Popen", "subprocess.call"} and isinstance(keywords.get("shell"), ast.Constant) and keywords["shell"].value is True:
                    rule = "subprocess_shell"
                elif name in {"yaml.load", "yaml.unsafe_load"} and (
                    name == "yaml.unsafe_load" or
                    not isinstance(keywords.get("Loader"), ast.Attribute) or
                    resolved_name(keywords["Loader"]) != "yaml.SafeLoader"
                ):
                    rule = "unsafe_yaml_load"
                elif name in {"requests.get", "requests.post", "requests.put", "requests.delete", "requests.request", "httpx.get", "httpx.post"} and isinstance(keywords.get("verify"), ast.Constant) and keywords["verify"].value is False:
                    rule = "disabled_tls_verification"
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                value = node.value
                if isinstance(value, ast.Constant) and isinstance(value.value, str) and len(value.value) >= 12:
                    if any(re.search(r"(?:api_?key|secret|password|token)", resolved_name(target), re.I) for target in targets):
                        rule = "hardcoded_secret"
            if rule:
                findings.append({
                    "rule": rule, "file": relative, "line": node.lineno,
                    "severity": "low" if is_test else "medium",
                    "context": "test_fixture" if is_test else "application",
                    "confidence": "heuristic",
                })
                if len(findings) >= 500:
                    break
        if len(findings) >= 500:
            break
    return {
        "status": "static_ast_scan", "files_scanned": scanned,
        "findings": findings, "finding_count": len(findings),
        "limitations": "Python AST-based triage only; no dataflow or exploitability verification. Test fixture findings are low priority. Non-Python security scanning is not included.",
    }


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
    """Suggest review targets, not missing tests; filename matching is unreliable."""
    candidates = []
    tests = []
    for path, relative, size in files:
        if path.suffix != ".py" or not (path.name.startswith("test_") or path.name.endswith("_test.py")):
            continue
        content = _text(path, size)
        if content is not None:
            tests.append(content)
    for path, relative, size in files:
        if path.suffix != ".py" or path.name.startswith("test_") or path.name.endswith("_test.py"):
            continue
        content = _text(path, size)
        if content is None:
            continue
        try:
            tree = ast.parse(content)
        except SyntaxError:
            continue
        functions = [
            node for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_")
        ]
        # Search is a weak signal only. Real coverage requires a matching execution trace.
        review = [node for node in functions if not any(
            re.search(r"\\b" + re.escape(node.name) + r"\\b", test) for test in tests
        )]
        if review:
            candidates.append({
                "source_file": relative,
                "functions_without_matching_test_file": [node.name for node in review[:50]],
                "function_locations": [
                    {"name": node.name, "line": node.lineno} for node in review[:50]
                ],
                "suggested_test_file": f"tests/test_{path.stem}.py",
                "evidence_type": "no_function_name_reference_in_test_sources",
                "verified_uncovered": False,
            })
        if len(candidates) >= 200:
            break
    return {
        "status": "candidate_analysis", "candidates": candidates, "count": len(candidates),
        "generated_code": False,
        "note": "Candidates have no detected function-name reference in test source. This is not execution coverage and does not prove missing tests.",
    }


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
