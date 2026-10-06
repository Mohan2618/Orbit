from app.services.qa_dimensions import inspect_repository
from app.services.qa_planner import create_plan


def test_static_dimensions_collect_bounded_evidence(tmp_path):
    (tmp_path / "index.html").write_text("<html><body>Hello</body></html>", encoding="utf-8")
    (tmp_path / "openapi.json").write_text('{"openapi":"3.1.0","info":{},"paths":{"/ping":{}}}', encoding="utf-8")
    (tmp_path / "unsafe.py").write_text("import subprocess\nsubprocess.run('x', shell=True)\n", encoding="utf-8")
    (tmp_path / "predictions.csv").write_text("label,prediction\na,a\n", encoding="utf-8")

    dimensions = inspect_repository(tmp_path)
    plan = create_plan({"languages": ["Python"]}, dimensions)

    assert dimensions["api"]["count"] == 1
    assert dimensions["ui"]["findings"]
    assert dimensions["security"]["finding_count"] >= 1
    assert dimensions["ml"]["count"] == 1
    assert dimensions["generation"]["generated_code"] is False
    assert any(item["check"] == "pytest_ruff_coverage" and item["status"] == "queued" for item in plan["selected_checks"])
