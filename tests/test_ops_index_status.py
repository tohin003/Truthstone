"""`agentguard index` and `doctor` say when the index is unavailable (R12).

R12 refuses to index $HOME, `/` and huge non-git trees, and `RepoIndex.status` says so
("building" | "ready" | "unavailable: <reason>"). The CLI never showed it:
`agentguard index ~` printed a column of zeros, which reads as an empty repository.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

import agentguard.cli.main as cli
from tests.test_doctor import doctor_env, run_doctor  # noqa: F401 - fixture

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fake_home(tmp_path, monkeypatch) -> Path:
    home = tmp_path / "user"
    (home / "notes").mkdir(parents=True)
    (home / "notes" / "todo.py").write_text("x = 1\n")
    monkeypatch.setenv("HOME", str(home))
    return home


def test_index_command_reports_unavailable_status(fake_home):
    result = CliRunner().invoke(cli.app, ["index", str(fake_home)])
    assert result.exit_code == 1, result.output
    assert "unavailable: the workspace is the home directory" in result.output
    assert "files" not in result.output, "no column of zeros that reads as an empty repository"


def test_index_command_reports_a_ready_index(tmp_path):
    repo = shutil.copytree(FIXTURES / "pyrepo", tmp_path / "pyrepo")
    result = CliRunner().invoke(cli.app, ["index", str(repo)])
    assert result.exit_code == 0, result.output
    assert "status        ready" in result.output
    assert "symbols" in result.output


def test_doctor_shows_the_workspace_index_status(doctor_env, fake_home, monkeypatch):  # noqa: F811
    monkeypatch.chdir(fake_home)
    code_home, at_home = run_doctor()
    index_part = at_home.split("\nindex\n", 1)[1]
    assert "unavailable: the workspace is the home directory" in index_part.splitlines()[0]
    assert index_part.splitlines()[0].lstrip().startswith("!"), "a warning, not a problem"

    repo = shutil.copytree(FIXTURES / "pyrepo", fake_home.parent / "pyrepo")
    monkeypatch.chdir(repo)
    code_repo, in_repo = run_doctor()
    first = in_repo.split("\nindex\n", 1)[1].splitlines()[0]
    assert "ready:" in first and "files" in first
    assert code_home == code_repo, "an unavailable index is not counted as a problem"


def test_doctor_reports_a_slow_build_as_building(doctor_env, tmp_path, monkeypatch):  # noqa: F811
    from agentguard.repo import index as repo_index

    repo = shutil.copytree(FIXTURES / "pyrepo", tmp_path / "slow")
    monkeypatch.chdir(repo)
    monkeypatch.setattr(cli, "DOCTOR_INDEX_WAIT_S", 0.0)
    monkeypatch.setattr(repo_index.RepoIndex, "build_async", lambda self: self)  # never finishes
    _, output = run_doctor()
    assert "still building after 0s" in output.split("\nindex\n", 1)[1].splitlines()[0]
