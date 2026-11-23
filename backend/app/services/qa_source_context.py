"""Safely capture small, line-numbered excerpts from analyzed source files."""

import ast
import re
from pathlib import Path

MAX_SNIPPETS = 120
MAX_LINE_LENGTH = 220
SECRET_ASSIGNMENT = re.compile(
    r"(?i)(api[_-]?key|secret|password|token)\s*[:=]\s*(['\\\"])[^'\\\"]+\2"
)


def _safe_line(line: str, kind: str) -> str:
    if len(line) > MAX_LINE_LENGTH:
        return "[line too long to display safely]"
    if kind == "hardcoded_secret":
        return "[potential credential redacted]"
    return SECRET_ASSIGNMENT.sub(r"\1 = '[redacted]'", line)


def capture_source_context(root: Path, dimensions: dict) -> dict[str, dict]:
    """Capture only approved relative paths and bounded excerpts; never full files."""
    output: dict[str, dict] = {}
    requests: list[tuple[str, int, str]] = []
    for finding in (dimensions.get("security") or {}).get("findings") or []:
        if isinstance(finding, dict) and type(finding.get("line")) is int:
            requests.append((str(finding.get("file") or ""), finding["line"], str(finding.get("rule") or "security")))
    for candidate in (dimensions.get("generation") or {}).get("candidates") or []:
        if not isinstance(candidate, dict):
            continue
        rel = str(candidate.get("source_file") or "")
        locations = candidate.get("function_locations")
        if isinstance(locations, list):
            for item in locations[:50]:
                if isinstance(item, dict) and type(item.get("line")) is int:
                    requests.append((rel, item["line"], "test coverage"))
        else:
            try:
                path = (root / rel).resolve()
                if not path.is_relative_to(root.resolve()) or path.is_symlink() or path.stat().st_size > 256_000:
                    continue
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, SyntaxError, ValueError):
                continue
            names = set(candidate.get("functions_without_matching_test_file") or [])
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names:
                    requests.append((rel, node.lineno, "test coverage"))
    for rel, line, kind in requests:
        if len(output) >= MAX_SNIPPETS:
            break
        if not rel or rel.startswith("/") or "\\" in rel or type(line) is not int or line < 1:
            continue
        try:
            path = (root / rel).resolve()
            if not path.is_relative_to(root.resolve()) or path.is_symlink() or path.stat().st_size > 256_000:
                continue
            lines = path.read_text(encoding="utf-8").splitlines()
            if line > len(lines):
                continue
            start, stop = max(1, line - 2), min(len(lines), line + 2)
            excerpt = "\n".join(
                f"{index}: {_safe_line(lines[index - 1], kind)}"
                for index in range(start, stop + 1)
            )
        except (OSError, UnicodeError, ValueError):
            continue
        output[f"{rel}:{line}"] = {
            "file": rel, "line": line, "source": excerpt,
            "kind": "test coverage" if kind == "test coverage" else "security",
        }
    return output
