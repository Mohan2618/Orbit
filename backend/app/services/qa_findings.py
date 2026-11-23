"""Explain non-fatal QA findings without treating heuristics as proven defects."""

import re

MAX_FINDINGS_PER_GROUP = 25
MAX_WARNING_TEXT = 20000

SECURITY_GUIDANCE = {
    "subprocess_shell": (
        "Possible shell command injection",
        "The scanner detected a subprocess pattern involving a shell. This may be harmless in tests or may allow unsafe command interpretation.",
        "Review whether untrusted input reaches a shell command. Prefer subprocess.run([...], shell=False) with separate arguments.",
        "subprocess.run(command, shell=True)",
        "subprocess.run(['python', 'script.py'], check=True)",
    ),
    "hardcoded_secret": (
        "Possible embedded credential",
        "A value resembles a secret embedded in source code. Test fixtures can trigger false positives.",
        "Verify whether the value is real. Revoke exposed credentials and load replacements from a secret manager or environment variable. Keep dummy test credentials clearly identified.",
        "API_KEY = 'real-key-here'",
        "API_KEY = os.environ['API_KEY']",
    ),
}

WARNING_GUIDANCE = {
    "PydanticDeprecatedSince20": (
        "Pydantic deprecated API",
        "The code uses a Pydantic API that is deprecated in version 2.",
        "Migrate the indicated API to its supported Pydantic v2 equivalent; check the warning text for the specific change.",
    ),
    "PytestCollectionWarning": (
        "Pytest collection warning",
        "Pytest found a class that resembles a test class but could not collect it.",
        "Check test naming and imports. If this is an application class, the warning may be harmless.",
    ),
    "StarletteDeprecationWarning": (
        "Starlette compatibility warning",
        "A test-client dependency is using a deprecated compatibility path.",
        "Review compatible Starlette and HTTPX versions before changing dependencies.",
    ),
    "UserWarning": (
        "Library configuration warning",
        "A dependency reported a configuration compatibility warning.",
        "Review the warning details and update the affected configuration where appropriate.",
    ),
}


def additional_findings(result: dict) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    dims = result.get("dimensions") or {}
    context = dims.get("source_context") or {}
    security = (dims.get("security") or {}).get("findings") or []
    for entry in security[:MAX_FINDINGS_PER_GROUP]:
        if not isinstance(entry, dict):
            continue
        rule = str(entry.get("rule") or "unknown")
        title, cause, fix, before, after = SECURITY_GUIDANCE.get(
            rule, ("Potential security issue", "A static pattern scanner flagged code for review.",
                   "Inspect the indicated source and validate whether the pattern is exploitable.", "", "")
        )
        path = str(entry.get("file") or "")
        line = entry.get("line")
        location = f"{path}:{line}" if path and isinstance(line, int) else path
        source_line = (context.get(location) or {}).get("source") or ""
        findings.append({
            "category": "security", "severity": str(entry.get("severity") or "review"),
            "tool": "Python AST security scan", "title": f"{title} ({location})" if location else title, "cause": (cause + (" This match is in a test file and may be a fixture." if entry.get("context") == "test_fixture" else "")), "fix": fix,
            "location": location, "location_kind": "detected" if location else "not_available",
            "responsible_file": "", "exit_code": "", "evidence": f"Rule: {rule}",
            "example_before": before, "example_after": after,
            "example_note": "The suggested correction is illustrative, not a verified patch. This is not a confirmed vulnerability.",
            "source_snippet": source_line,
        })

    candidates = (dims.get("generation") or {}).get("candidates") or []
    for candidate in candidates[:MAX_FINDINGS_PER_GROUP]:
        if not isinstance(candidate, dict):
            continue
        funcs = [str(name) for name in (candidate.get("functions_without_matching_test_file") or [])][:12]
        source = str(candidate.get("source_file") or "")
        target = str(candidate.get("suggested_test_file") or "")
        source_entries = [
            value for value in context.values()
            if isinstance(value, dict) and value.get("file") == source
            and value.get("kind") == "test coverage"
        ][:12]
        source_entries.sort(key=lambda value: value["line"])
        findings.append({
            "category": "test coverage", "severity": "info", "tool": "test reference heuristic",
            "title": f"Test review: {source}" if source else "Potential test coverage gap",
            "cause": "No function-name reference was found in the inspected test sources for: " + (", ".join(funcs) or "unknown") + ". This does not prove they are untested. Runtime coverage and indirect or integration tests may cover them.",
            "fix": f"Inspect actual coverage and existing integration tests before writing new tests. Candidate test module: {target or 'choose an appropriate test module'}.",
            "location": source, "location_kind": "source file" if source else "not_available",
            "source_snippet": "\n".join(str(entry["line"]) + ": " + str(entry["source"]) for entry in source_entries),
            "responsible_file": "", "exit_code": "", "evidence": "",
            "example_before": "", "example_after": "", "example_note": "",
        })

    output = str(result.get("output") or "")[:MAX_WARNING_TEXT]
    # Parse the pytest warnings-summary layout, not arbitrary traceback lines.
    summary = output.split("warnings summary", 1)
    if len(summary) == 2:
        section = summary[1].split("-- Docs:", 1)[0]
        pattern = re.compile(
            r"(?m)^(?P<path>(?:\.\./)?(?:workspace/)?[^\n]+?\.py):(?P<line>\d+)(?:\s+\([^\n]*\))?\n"
            r"\s+(?:[^\n:]+\.py:\d+:\s*)?(?P<kind>PydanticDeprecatedSince20|PytestCollectionWarning|StarletteDeprecationWarning|UserWarning):\s*(?P<message>[^\n]+)"
        )
        seen: set[tuple[str, str, str]] = set()
        for match in pattern.finditer(section):
            path = match.group("path")
            kind = match.group("kind")
            key = (path, match.group("line"), kind)
            if key in seen:
                continue
            seen.add(key)
            title, cause, fix = WARNING_GUIDANCE[kind]
            message = match.group("message")
            if kind == "PydanticDeprecatedSince20":
                if "class-based" in message:
                    title = "Pydantic class Config is deprecated"
                    fix = "Replace class Config with model_config = ConfigDict(...), preserving existing settings. Import ConfigDict from pydantic."
                elif "Field" in message and "example" in message:
                    title = "Pydantic Field(example=...) is deprecated"
                    fix = "Move the example into json_schema_extra={'example': ...} on Field, preserving the original example value."
                elif "from_orm" in message:
                    title = "Pydantic from_orm() is deprecated"
                    fix = "Configure from_attributes=True and use model_validate(instance)."
                elif "dict" in message:
                    title = "Pydantic dict() is deprecated"
                    fix = "Use model_dump() instead of dict()."
            findings.append({
                "category": "compatibility", "severity": "warning", "tool": "pytest warnings",
                "title": title, "cause": cause, "fix": fix,
                "location": f"{path}:{match.group('line')}", "location_kind": "reported",
                "responsible_file": "", "exit_code": "", "evidence": match.group("message")[:500],
                "example_before": "", "example_after": "",
                "example_note": "A dependency warning may refer to library code rather than the analyzed repository.",
            })
            if len(seen) >= MAX_FINDINGS_PER_GROUP:
                break
    return findings
