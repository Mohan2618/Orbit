"""Fetch repositories and execute their Python tests in disposable Docker sandboxes."""

from __future__ import annotations

import asyncio
from io import BytesIO
import json
from pathlib import Path
import re
import tarfile
import tempfile
import time
import uuid

import docker
from docker.errors import APIError, DockerException, ImageNotFound
from requests.exceptions import ReadTimeout as RequestsReadTimeout
from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.test_run import TestRun
from app.services.repository_archive import download_repository
from app.services.repository_intelligence import parse_github_repository_url
from app.services.qa_planner import create_plan
from app.services.qa_dimensions import inspect_repository

RUNNER_IMAGE = "orbit-api:local"
MAX_INSTALL_PACKAGES = 40
SANDBOX_MEMORY = "768m"
SANDBOX_CPUS = 1_000_000_000
SANDBOX_PIDS = 128
MAX_PYTEST_SECONDS = 240
MAX_WHEELHOUSE_BYTES = 512 * 1024 * 1024
MAX_WHEELHOUSE_FILES = 300


def execute_test_run(test_run_id: str) -> dict:
    with SessionLocal() as session:
        test_run = session.scalar(select(TestRun).where(TestRun.id == test_run_id))
        if test_run is None:
            raise ValueError("Test run not found.")
        repository_url = test_run.repository_url
        generated_test_id = test_run.generated_test_id
        generated_test = None
        if generated_test_id:
            from app.models.generated_test import GeneratedTest

            generated_test = session.get(GeneratedTest, generated_test_id)
            if generated_test is None or not generated_test.approved:
                raise ValueError("The generated test is missing or has not been approved.")
            generated_test = {
                "id": generated_test.id,
                "repository_url": generated_test.repository_url,
                "source_path": generated_test.source_path,
                "test_code": generated_test.test_code,
            }

    client = docker.from_env(timeout=180)
    try:
        client.ping()
    except DockerException as exc:
        client.close()
        raise RuntimeError("The isolated Docker runner is unavailable.") from exc

    run_suffix = uuid.uuid4().hex[:12]
    labels = {"com.orbit.managed": "true", "com.orbit.test-run": test_run_id}
    volumes = []
    containers = []
    started = time.monotonic()
    try:
        _cleanup_run_resources(client, test_run_id)
        with tempfile.TemporaryDirectory(prefix=f"orbit-{run_suffix}-") as temporary_directory:
            source = Path(temporary_directory) / "source"
            discovery = asyncio.run(download_repository(repository_url, source))
            if generated_test:
                target_repo = parse_github_repository_url(repository_url)
                candidate_repo = parse_github_repository_url(generated_test["repository_url"])
                if (target_repo.owner.casefold(), target_repo.name.casefold()) != (
                    candidate_repo.owner.casefold(), candidate_repo.name.casefold()
                ):
                    raise ValueError("The approved generated test belongs to a different repository.")
                import ast

                ast.parse(generated_test["test_code"])
                generated_path = source / "tests" / f"test_orbit_generated_{generated_test['id'].replace('-', '')}.py"
                generated_path.parent.mkdir(exist_ok=True)
                generated_path.write_text(generated_test["test_code"], encoding="utf-8")
            dimensions = inspect_repository(source)
            if "Python" not in discovery["languages"]:
                return {
                    "outcome": "unsupported_language",
                    "error_message": "The executable QA runner currently supports Python repositories only.",
                    "repository": discovery,
                    "dimensions": dimensions,
                    "qa_plan": create_plan(discovery, dimensions),
                    "duration_seconds": round(time.monotonic() - started, 3),
                }

            packages = _safe_package_names(discovery["dependencies"])
            runner_packages = sorted({*packages, "pytest-cov", "ruff"})
            workspace_volume = client.volumes.create(
                name=f"orbit-run-{run_suffix}-workspace", labels=labels
            )
            wheel_volume = client.volumes.create(
                name=f"orbit-run-{run_suffix}-wheels", labels=labels
            )
            volumes.extend([workspace_volume, wheel_volume])
            _prepare_volume(client, run_suffix, labels, workspace_volume, "/workspace", containers)
            _prepare_volume(client, run_suffix, labels, wheel_volume, "/wheelhouse", containers)

            download_result = _download_dependency_wheels(
                client, run_suffix, labels, wheel_volume, runner_packages, containers
            )
            if download_result is not None:
                return {
                    **download_result,
                    "repository": discovery,
                    "duration_seconds": round(time.monotonic() - started, 3),
                }
            _enforce_wheelhouse_limits(client, suffix=run_suffix, labels=labels, wheel_volume=wheel_volume)

            _copy_source_to_volume(client, run_suffix, labels, workspace_volume, source, containers)
            report = _run_pytest_sandbox(
                client, run_suffix, labels, workspace_volume, wheel_volume, runner_packages, containers
            )
            report["repository"] = discovery
            report["dimensions"] = dimensions
            report["qa_plan"] = create_plan(discovery, dimensions)
            if generated_test:
                report["generated_test"] = {
                    "id": generated_test["id"],
                    "source_path": generated_test["source_path"],
                    "execution_file": "tests/test_orbit_generated_<id>.py",
                }
            report["duration_seconds"] = round(time.monotonic() - started, 3)
            report["execution_limits"] = {
                "network": "disabled during dependency installation and tests",
                "memory": SANDBOX_MEMORY,
                "cpu_nanocpus": SANDBOX_CPUS,
                "processes": SANDBOX_PIDS,
                "pytest_timeout_seconds": MAX_PYTEST_SECONDS,
                "dependency_download": "binary wheels only from the public Python package index",
            }
            return report
    except (DockerException, OSError, tarfile.TarError) as exc:
        raise RuntimeError(f"The isolated QA run could not start: {exc}") from exc
    finally:
        for container in reversed(containers):
            try:
                container.remove(force=True, v=True)
            except DockerException:
                pass
        for volume in reversed(volumes):
            try:
                volume.remove(force=True)
            except DockerException:
                pass
        client.close()


def _cleanup_run_resources(client, test_run_id: str) -> None:
    filter_labels = [f"com.orbit.test-run={test_run_id}"]
    for container in client.containers.list(all=True, filters={"label": filter_labels}):
        try:
            container.remove(force=True, v=True)
        except DockerException:
            pass
    for volume in client.volumes.list(filters={"label": filter_labels}):
        try:
            volume.remove(force=True)
        except DockerException:
            pass


def _prepare_volume(client, suffix, labels, volume, mount_path, containers) -> None:
    """Make a fresh Docker volume writable by the unprivileged transfer containers."""
    container = client.containers.run(
        RUNNER_IMAGE,
        name=f"orbit-run-{suffix}-prepare-{volume.name.rsplit('-', 1)[-1]}",
        command=["python", "-c", f"import os; os.chmod({mount_path!r}, 0o777)"],
        detach=True,
        remove=False,
        labels=labels,
        network_mode="none",
        volumes={volume.name: {"bind": mount_path, "mode": "rw"}},
        read_only=True,
        user="0:0",
        cap_drop=["ALL"],
        security_opt=["no-new-privileges:true"],
        mem_limit="64m",
        nano_cpus=250_000_000,
        pids_limit=16,
        tmpfs={"/tmp": "rw,noexec,nosuid,size=8m"},
    )
    containers.append(container)
    status, logs = _wait(container, timeout=15)
    if status != 0:
        raise RuntimeError("A temporary runner volume could not be prepared for unprivileged access.")


def _safe_package_names(packages: list[str]) -> list[str]:
    if len(packages) > MAX_INSTALL_PACKAGES:
        raise ValueError("This repository declares more than 40 Python dependencies.")
    if any(
        not isinstance(package, str)
        or len(package) > 100
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", package) is None
        for package in packages
    ):
        raise ValueError("The repository contains a dependency name the isolated runner cannot install safely.")
    return sorted(
        {package.lower().replace("_", "-") for package in packages if package.lower() != "pytest"}
    )


def _hardening() -> dict:
    return {
        "read_only": True,
        "user": "65534:65534",
        "cap_drop": ["ALL"],
        "security_opt": ["no-new-privileges:true"],
        "mem_limit": SANDBOX_MEMORY,
        "nano_cpus": SANDBOX_CPUS,
        "pids_limit": SANDBOX_PIDS,
        "tmpfs": {"/tmp": "rw,noexec,nosuid,size=128m"},
        "environment": {"HOME": "/tmp", "PYTHONDONTWRITEBYTECODE": "1"},
    }


def _wait(container, timeout: int) -> tuple[int | None, bytes]:
    try:
        status = container.wait(timeout=timeout)
        return status.get("StatusCode", 1), container.logs(stdout=True, stderr=True, tail=200)
    except RequestsReadTimeout:
        container.kill()
        return None, b"Container exceeded its time limit."


def _download_dependency_wheels(client, suffix, labels, wheel_volume, packages, containers):
    if not packages:
        return None
    try:
        command = [
            "python",
            "-m",
            "pip",
            "download",
            "--disable-pip-version-check",
            "--no-cache-dir",
            "--only-binary=:all:",
            "--index-url",
            "https://pypi.org/simple",
            "--dest",
            "/wheelhouse",
            *packages,
        ]
        container = client.containers.run(
            RUNNER_IMAGE,
            name=f"orbit-run-{suffix}-download",
            command=command,
            detach=True,
            remove=False,
            labels=labels,
            network_mode="bridge",
            volumes={wheel_volume.name: {"bind": "/wheelhouse", "mode": "rw"}},
            read_only=True,
            user="65534:65534",
            cap_drop=["ALL"],
            security_opt=["no-new-privileges:true"],
            mem_limit=SANDBOX_MEMORY,
            nano_cpus=SANDBOX_CPUS,
            pids_limit=SANDBOX_PIDS,
            tmpfs={"/tmp": "rw,noexec,nosuid,size=128m"},
            environment={
                "HOME": "/tmp",
                "PIP_CONFIG_FILE": "/dev/null",
                "PIP_NO_CACHE_DIR": "1",
                "PYTHONDONTWRITEBYTECODE": "1",
            },
        )
        containers.append(container)
        status, logs = _wait(container, timeout=180)
        if status != 0:
            return {
                "outcome": "dependency_resolution_failed",
                "error_message": "Python dependencies could not be resolved as binary wheels from PyPI.",
                "steps": [{"name": "download_dependencies", "return_code": status}],
                "output": logs.decode("utf-8", errors="replace")[-1024 * 1024 :],
            }
        return None
    except (APIError, ImageNotFound, DockerException) as exc:
        raise RuntimeError("The dependency download sandbox could not start.") from exc


def _enforce_wheelhouse_limits(client, suffix, labels, wheel_volume) -> None:
    inspect_script = (
        "import json,pathlib; p=list(pathlib.Path('/wheelhouse').iterdir()); "
        "print(json.dumps({'files':len(p),'bytes':sum(x.stat().st_size for x in p if x.is_file())}))"
    )
    try:
        output = client.containers.run(
            RUNNER_IMAGE,
            name=f"orbit-run-{suffix}-wheelcheck",
            command=["python", "-c", inspect_script],
            remove=True,
            labels=labels,
            network_mode="none",
            volumes={wheel_volume.name: {"bind": "/wheelhouse", "mode": "ro"}},
            read_only=True,
            user="65534:65534",
            cap_drop=["ALL"],
            security_opt=["no-new-privileges:true"],
            mem_limit="64m",
            nano_cpus=250_000_000,
            pids_limit=16,
            tmpfs={"/tmp": "rw,noexec,nosuid,size=8m"},
        )
        usage = json.loads(output.decode("utf-8"))
    except (APIError, ImageNotFound, DockerException, ValueError, UnicodeDecodeError) as exc:
        raise RuntimeError("The dependency wheelhouse could not be inspected safely.") from exc
    if usage.get("bytes", MAX_WHEELHOUSE_BYTES + 1) > MAX_WHEELHOUSE_BYTES or usage.get("files", MAX_WHEELHOUSE_FILES + 1) > MAX_WHEELHOUSE_FILES:
        raise ValueError("Resolved Python dependencies exceed the 512 MiB or 300 wheel-file limit.")


def _copy_source_to_volume(client, suffix, labels, workspace_volume, source, containers) -> None:
    loader = client.containers.run(
        RUNNER_IMAGE,
        name=f"orbit-run-{suffix}-loader",
        command=["python", "-c", "import time; time.sleep(600)"],
        detach=True,
        remove=False,
        labels=labels,
        network_mode="none",
        volumes={workspace_volume.name: {"bind": "/workspace", "mode": "rw"}},
        **_hardening(),
    )
    containers.append(loader)
    archive = BytesIO()
    with tarfile.open(fileobj=archive, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for path in source.rglob("*"):
            if path.is_file() and not path.is_symlink():
                tar.add(path, arcname=path.relative_to(source).as_posix(), recursive=False)
    if not loader.put_archive("/workspace", archive.getvalue()):
        raise RuntimeError("The repository could not be copied into the isolated runner.")
    loader.stop(timeout=1)


def _run_pytest_sandbox(client, suffix, labels, workspace_volume, wheel_volume, packages, containers):
    container = client.containers.run(
        RUNNER_IMAGE,
        name=f"orbit-run-{suffix}-pytest",
        command=["python", "/app/app/execution/runner_entrypoint.py"],
        detach=True,
        remove=False,
        labels=labels,
        network_mode="none",
        volumes={
            workspace_volume.name: {"bind": "/workspace", "mode": "ro"},
            wheel_volume.name: {"bind": "/wheelhouse", "mode": "ro"},
        },
        working_dir="/workspace",
        environment={
            **_hardening()["environment"],
            "ORBIT_PACKAGES": json.dumps(packages),
        },
        **{key: value for key, value in _hardening().items() if key != "environment"},
    )
    containers.append(container)
    status, logs = _wait(container, timeout=420)
    lines = logs.decode("utf-8", errors="replace").splitlines()
    for line in reversed(lines):
        try:
            report = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(report, dict) and "outcome" in report:
            return report
    return {
        "outcome": "runner_failed" if status is not None else "timed_out",
        "error_message": "The isolated runner did not produce a result report.",
        "steps": [],
        "output": "\n".join(lines)[-1024 * 1024 :],
    }
