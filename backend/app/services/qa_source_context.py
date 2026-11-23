"""Bounded source context captured during the same repository QA run.

Only known, inspected paths are read. Secret-like values are never persisted.
"""

import ast
import re
from pathlib import Path

MAX_SNIPPETS = 80
MAX_LINE_LENGTH = 220
SENSITIVE = re.compile(r"(?i)(api[_-]?key|secret|password|token)\s*[:=]\s*['\"][^'\"]+['\"]")
QUOTED = re.compile(r"(['\"])(?:\\.|(?!\1).)*?\1")


def _safe_line(line: str, *, security: bool = False) -> str:
    if len(line) > MAX_LINE_LENGTH:
        return "[line too long to display safely]"
    if SENSITIVE.search(line):
        return "[potential credential redacted]"
    if security:
        # Security scan evidence may contain secrets outside assignment syntax.
        return QUOTED.sub('"[redacted]"', line)
    return line


def capture_source_context(root: Path, dimensions: dict) -> dict[str, dict]:
    """Store only limited relevant lines, not entire repository files."""
    output: dict[str, dict] = {}
    security = (dimensions.get("security") or {}).get("findings") or []
    candidates = (dimensions.get("generation") or {}).get("candidates") or []
    requests: list[tuple[str, int, str]] = []
    for finding in security:
        if isinstance(finding, dict) and isinstance(finding.get("line"), int):
            requests.append((str(finding.get("file") or ""), finding["line"], "security"))
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        rel = str(candidate.get("source_file") or "")
        try:
            path = (root / rel).resolve()
            if not path.is_relative_to(root.resolve()) or path.is_symlink() or path.stat().st_size > 256_000:
                continue
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (OSError, UnicodeError, SyntaxError, ValueError):
            continue
        names = set(candidate.get("functions_without_matching_test_file") or [])
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names:
                requests.append((rel, node.lineno, "test coverage"))
    for rel, line, kind in requests:
        if len(output) >= MAX_SNIPPETS:
            break
        if not rel or rel.startswith("/") or "\\" in rel or not isinstance(line, int) or line < 1:
            continue
        try:
            path = (root / rel).resolve()
            if not path.is_relative_to(root.resolve()) or path.is_symlink() or path.stat().st_size > 256_000:
                continue
            lines = path.read_text(encoding="utf-8").splitlines()
            if line > len(lines):
                continue
            actual = _safe_line(lines[line - 1], security=kind == "security")
        except (OSError, UnicodeError, ValueError):
            continue
        output[f"{rel}:{line}"] = {"file": rel, "line": line, "source": actual, "kind": kind}
    return output
