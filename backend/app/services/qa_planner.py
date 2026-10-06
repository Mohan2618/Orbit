"""Rule-based QA plan selection with an auditable reason for each check."""


def create_plan(repository: dict, dimensions: dict) -> dict:
    languages = set(repository.get("languages", []))
    plan = [
        {"check": "repository_discovery", "status": "complete", "reason": "GitHub metadata, source tree, and supported manifests were inspected."},
        {"check": "security_patterns", "status": "complete", "reason": "Bounded source files were scanned for common unsafe patterns."},
        {"check": "performance_footprint", "status": "complete", "reason": "Source size and unusually large files were measured without starting the application."},
        {"check": "ui_accessibility_static", "status": "complete" if dimensions.get("ui", {}).get("html_file_count") else "skipped", "reason": "HTML files were found." if dimensions.get("ui", {}).get("html_file_count") else "No HTML files were discovered."},
        {"check": "api_specification_static", "status": "complete" if dimensions.get("api", {}).get("count") else "skipped", "reason": "OpenAPI/Swagger specification files were found." if dimensions.get("api", {}).get("count") else "No supported OpenAPI/Swagger JSON specification was discovered."},
        {"check": "ml_dataset_discovery", "status": "complete" if dimensions.get("ml", {}).get("count") else "skipped", "reason": "Evaluation/prediction data files were found." if dimensions.get("ml", {}).get("count") else "No evaluation dataset artifact was discovered."},
        {"check": "test_gap_analysis", "status": "complete" if "Python" in languages else "skipped", "reason": "Python source files were inspected for public functions without a matching test file." if "Python" in languages else "The candidate generator currently inspects Python source only."},
        {"check": "pytest_ruff_coverage", "status": "queued" if "Python" in languages else "unsupported", "reason": "The isolated executable runner currently supports Python repositories." if "Python" in languages else "No executable runner is enabled for this repository language."},
    ]
    return {
        "planner": "orbit-rules-v1",
        "selected_checks": plan,
        "autonomous_retesting": "not_enabled; model-generated tests require human approval before execution",
    }
