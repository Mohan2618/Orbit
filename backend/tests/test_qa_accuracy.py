from pathlib import Path

from app.services.qa_dimensions import inspect_repository
from app.services.qa_source_context import capture_source_context


def test_security_ignores_examples_inside_strings(tmp_path: Path):
    (tmp_path / "example.py").write_text(
        'RULE = "subprocess.run(command, shell=True)"\n'
        'SECRET = "api_key = \'not-a-real-secret\'"\n',
        encoding="utf-8",
    )
    assert inspect_repository(tmp_path)["security"]["finding_count"] == 0


def test_security_finds_executable_shell_call(tmp_path: Path):
    (tmp_path / "main.py").write_text(
        "import subprocess\nsubprocess.run(command, shell=True)\n", encoding="utf-8"
    )
    dims = inspect_repository(tmp_path)
    assert dims["security"]["findings"][0]["line"] == 2
    assert dims["security"]["findings"][0]["rule"] == "subprocess_shell"
    context = capture_source_context(tmp_path, dims)
    assert "2: subprocess.run(command, shell=True)" in context["main.py:2"]["source"]


def test_security_marks_test_fixture_as_low_priority(tmp_path: Path):
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_sample.py").write_text(
        "api_key = 'dummy-example-credential'\n", encoding="utf-8"
    )
    finding = inspect_repository(tmp_path)["security"]["findings"][0]
    assert finding["severity"] == "low"
    assert finding["context"] == "test_fixture"


def test_test_review_exposes_function_line_without_claiming_missing_coverage(tmp_path: Path):
    (tmp_path / "service.py").write_text(
        "\ndef compute(value):\n    return value + 1\n", encoding="utf-8"
    )
    dims = inspect_repository(tmp_path)
    item = dims["generation"]["candidates"][0]
    assert item["function_locations"] == [{"name": "compute", "line": 2}]
    assert item["verified_uncovered"] is False
    context = capture_source_context(tmp_path, dims)
    assert "2: def compute(value):" in context["service.py:2"]["source"]


def test_test_reference_removes_named_candidate(tmp_path: Path):
    (tmp_path / "service.py").write_text("def compute():\n    return 1\n", encoding="utf-8")
    (tmp_path / "test_service.py").write_text(
        "from service import compute\ndef test_compute():\n    assert compute() == 1\n",
        encoding="utf-8",
    )
    assert inspect_repository(tmp_path)["generation"]["count"] == 0
