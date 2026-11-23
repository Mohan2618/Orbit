from app.services.error_explanations import explain_result


def test_ruff_finding_has_actionable_explanation():
    result = {"steps": [{"name": "ruff", "return_code": 1}],
              "static_analysis": {"findings": [{"code": "F401", "message": "unused import",
                                                 "filename": "app.py", "line": 2}]}}
    items = explain_result(result)
    assert len(items) == 1
    assert items[0]["category"] == "repository"
    assert items[0]["location"] == "app.py:2"
    assert "Remove" in items[0]["fix"]


def test_sandbox_cache_error_is_infrastructure_not_repository():
    result = {"steps": [{"name": "ruff", "return_code": 2}],
              "static_analysis": {"findings": [], "output": "Failed to initialize cache: Read-only file system"}}
    items = explain_result(result)
    assert items[0]["category"] == "infrastructure"
    assert "--no-cache" in items[0]["fix"]


def test_pytest_failure_and_no_tests():
    failure = explain_result({"steps": [{"name": "pytest", "return_code": 1}],
                              "output": "FAILED tests/test_math.py::test_add - AssertionError"})
    assert failure[0]["location"] == "tests/test_math.py::test_add"
    missing = explain_result({"steps": [{"name": "pytest", "return_code": 5}]})
    assert missing[0]["title"] == "No tests discovered"


def test_clean_run_has_no_error_explanations():
    result = {"steps": [{"name": "ruff", "return_code": 0},
                        {"name": "pytest", "return_code": 0}],
              "static_analysis": {"findings": []}}
    assert explain_result(result) == []


def test_dependency_failure_and_timeout():
    result = {"steps": [{"name": "install_dependencies", "return_code": 1},
                        {"name": "pytest", "timed_out": True, "return_code": None}]}
    items = explain_result(result)
    assert {item["tool"] for item in items} == {"dependencies", "pytest"}
