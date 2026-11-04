"""M6 — the CI workflow runs what it claims to, where it claims to."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


@pytest.fixture(scope="module")
def workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def runs(job: dict) -> list[str]:
    return [" ".join(step["run"].split()) for step in job["steps"] if "run" in step]


def uses(job: dict) -> list[str]:
    return [step["uses"] for step in job["steps"] if "uses" in step]


def test_it_runs_on_pushes_and_pull_requests(workflow):
    triggers = workflow.get("on", workflow.get(True))  # YAML 1.1 reads a bare `on` as True
    assert "push" in triggers and "pull_request" in triggers
    assert workflow["permissions"] == {"contents": "read"}


def test_the_blocking_matrix(workflow):
    job = workflow["jobs"]["test"]
    matrix = job["strategy"]["matrix"]
    assert sorted(matrix["os"]) == ["macos-latest", "ubuntu-latest"]
    assert matrix["python"] == ["3.12", "3.13"], "quoted, or YAML reads 3.10 as 3.1"
    assert sorted(matrix["extras"]) == ["all-extras", "base"]
    assert job["strategy"]["fail-fast"] is False
    assert "continue-on-error" not in job, "Linux and macOS block a merge"
    assert job["runs-on"] == "${{ matrix.os }}"


def test_python_versions_match_the_project(workflow):
    requires = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["requires-python"]
    assert requires == ">=3.12"
    versions = workflow["jobs"]["test"]["strategy"]["matrix"]["python"]
    assert all(tuple(map(int, v.split("."))) >= (3, 12) for v in versions)


def test_each_extras_flavour_installs_what_it_says(workflow):
    steps = workflow["jobs"]["test"]["steps"]
    syncs = {
        step.get("if"): " ".join(step["run"].split()) for step in steps if "uv sync" in step.get("run", "")
    }
    assert syncs == {
        "matrix.extras == 'base'": "uv sync",
        "matrix.extras == 'all-extras'": "uv sync --all-extras",
    }


@pytest.mark.parametrize("name", ["test", "windows"])
def test_every_job_checks_out_installs_lints_and_tests(workflow, name):
    job = workflow["jobs"][name]
    actions = uses(job)
    assert any(a.startswith("actions/checkout@") for a in actions)
    assert any(a.startswith("astral-sh/setup-uv@") for a in actions)
    commands = runs(job)
    assert "uv run ruff check src tests" in commands
    assert "uv run pytest -q" in commands
    assert commands.index("uv run ruff check src tests") < commands.index("uv run pytest -q")


@pytest.mark.parametrize("name", ["test", "windows"])
def test_every_job_uses_a_temporary_agentguard_home(workflow, name):
    job = workflow["jobs"][name]
    setters = [step for step in job["steps"] if "AGENTGUARD_HOME=" in step.get("run", "")]
    assert len(setters) == 1
    step = setters[0]
    assert '$RUNNER_TEMP' in step["run"] and '"$GITHUB_ENV"' in step["run"] and step["shell"] == "bash"
    # ...before anything installs or runs.
    assert job["steps"].index(step) < min(i for i, s in enumerate(job["steps"]) if "uv " in s.get("run", ""))


def test_windows_is_informational_and_never_blocks(workflow):
    job = workflow["jobs"]["windows"]
    assert job["runs-on"] == "windows-latest"
    assert job["continue-on-error"] is True
    assert set(workflow["jobs"]) == {"test", "windows"}
