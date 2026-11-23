from app.services.qa_findings import additional_findings


def test_security_finding_has_grounded_location_and_disclaimer():
    result = {"dimensions": {"security": {"findings": [
        {"rule": "hardcoded_secret", "file": "tests/test_auth.py", "line": 11, "severity": "medium"}
    ]}}}
    items = additional_findings(result)
    assert len(items) == 1
    assert items[0]["location"] == "tests/test_auth.py:11"
    assert "not a confirmed vulnerability" in items[0]["example_note"]
    assert items[0]["example_after"]


def test_gap_candidate_is_informational_not_proven_missing_test():
    result = {"dimensions": {"generation": {"candidates": [
        {"source_file": "app/main.py", "functions_without_matching_test_file": ["main"],
         "suggested_test_file": "tests/test_main.py"}
    ]}}}
    items = additional_findings(result)
    assert items[0]["severity"] == "info"
    assert "does not prove" in items[0]["cause"]
    assert "tests/test_main.py" in items[0]["fix"]


def test_deprecation_warning_reports_actual_path():
    result = {"output": (
        "================ warnings summary ================\n"
        "../workspace/app/schemas/item.py:14\n"
        "  app/schemas/item.py:14: PydanticDeprecatedSince20: class Config is deprecated\n"
        "-- Docs: https://docs.pytest.org/\n"
    )}
    items = additional_findings(result)
    assert len(items) == 1
    assert items[0]["category"] == "compatibility"
    assert items[0]["location"].endswith("item.py:14")


def test_clean_run_and_malformed_findings_are_safe():
    assert additional_findings({}) == []
    assert additional_findings({"dimensions": {"security": {"findings": [None]}}}) == []


def test_findings_are_bounded():
    items = [{"rule": "unknown", "file": "app.py", "line": i} for i in range(100)]
    assert len(additional_findings({"dimensions": {"security": {"findings": items}}})) == 25
