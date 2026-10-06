import pytest

from app.services.qa_execution import _hardening, _safe_package_names


def test_dependency_names_are_deduplicated_and_pytest_uses_base_image():
    assert _safe_package_names(["pytest", "FastAPI", "fastapi"]) == ["fastapi"]


@pytest.mark.parametrize("name", ["-index-url", "foo/bar", "pkg;touch /tmp/x", "https://evil.invalid/a.whl"])
def test_dependency_names_reject_options_urls_and_shell_syntax(name):
    with pytest.raises(ValueError):
        _safe_package_names([name])


def test_sandbox_uses_non_root_and_restricted_filesystem_defaults():
    limits = _hardening()

    assert limits["read_only"] is True
    assert limits["user"] == "65534:65534"
    assert limits["cap_drop"] == ["ALL"]
    assert limits["security_opt"] == ["no-new-privileges:true"]
    assert limits["mem_limit"] == "768m"
    assert limits["pids_limit"] == 128
    assert "/tmp" in limits["tmpfs"]
