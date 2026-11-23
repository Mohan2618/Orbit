from pathlib import Path

from app.services.qa_source_context import capture_source_context


def test_captures_actual_function_definition_and_line(tmp_path: Path):
    path = tmp_path / "app.py"
    path.write_text("x = 1\n\ndef calculate(value):\n    return value + 1\n", encoding="utf-8")
    dimensions = {"generation": {"candidates": [{
        "source_file": "app.py", "functions_without_matching_test_file": ["calculate"]
    }]}}
    context = capture_source_context(tmp_path, dimensions)
    assert "3: def calculate(value):" in context["app.py:3"]["source"]
    assert "4:     return value + 1" in context["app.py:3"]["source"]
    assert context["app.py:3"]["line"] == 3


def test_redacts_possible_secret_in_source(tmp_path: Path):
    (tmp_path / "auth.py").write_text("api_key = 'super-secret-value'\n", encoding="utf-8")
    dimensions = {"security": {"findings": [{
        "rule": "hardcoded_secret", "file": "auth.py", "line": 1
    }]}}
    context = capture_source_context(tmp_path, dimensions)
    assert "super-secret-value" not in str(context)
    assert "redacted" in context["auth.py:1"]["source"]


def test_rejects_path_traversal(tmp_path: Path):
    dimensions = {"security": {"findings": [
        {"rule": "subprocess_shell", "file": "../outside.py", "line": 1}
    ]}}
    assert capture_source_context(tmp_path, dimensions) == {}
