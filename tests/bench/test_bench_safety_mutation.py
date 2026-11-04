"""Audit M4 (and the M2 counter fix) for the original Claude harness and the mutation bench.

* The live harness resets and cleans the repository it runs in, so it must refuse
  anything but a clean scratch copy. The documented command once pointed it at ``.``.
* ``summarize`` counted errors over rows already filtered to error-free ones: always 0.
* Mutation precision was vacuous (0 claims checked). It is now a fresh-file replay that
  must check claims, and the sample is seeded and stratified.
"""

from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path

import pytest

from truthstone.bench import mutation, runner
from truthstone.repo.index import RepoIndex


def _repo(path: Path) -> Path:
    path.mkdir(parents=True)
    (path / "app.py").write_text("x = 1\n")
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=path, check=True)
    subprocess.run(
        ["git", "-c", "user.email=a@b", "-c", "user.name=a", "commit", "-qm", "i"], cwd=path, check=True
    )
    return path


def test_the_harness_refuses_a_repository_that_is_not_a_scratch_copy(tmp_path):
    real = _repo(tmp_path / "real")
    (real / "work-in-progress.txt").write_text("precious")
    with pytest.raises(runner.BenchSafetyError, match="not a scratch copy"):
        runner.run(real, tmp_path / "settings.json", ["false-completion"], 1, tmp_path / "out.json")
    with pytest.raises(runner.BenchSafetyError):
        runner.reset(real)
    assert (real / "work-in-progress.txt").read_text() == "precious"


def test_the_harness_refuses_its_own_source_tree():
    with pytest.raises(runner.BenchSafetyError, match="source tree"):
        runner.assert_scratch(Path(runner.__file__).resolve().parents[3])


def test_a_scratch_copy_is_accepted_until_it_is_dirty(tmp_path):
    source = _repo(tmp_path / "source")
    scratch = runner.prepare_repo(source, tmp_path / "scratch")
    assert (scratch / runner.SCRATCH_MARKER).is_file()
    runner.assert_scratch(scratch)
    (scratch / "app.py").write_text("x = 2\n")
    with pytest.raises(runner.BenchSafetyError, match="uncommitted"):
        runner.assert_scratch(scratch)
    with pytest.raises(runner.BenchSafetyError):
        runner.prepare_repo(source, source / "nested")
    with pytest.raises(runner.BenchSafetyError, match="not a scratch copy"):
        runner.prepare_repo(source, source)


def test_summarize_counts_errors_and_voids():
    rows = [
        {
            "arm": "control",
            "error": "",
            "hallucinated_refs": 0,
            "unnecessary_files": 0,
            "false_completion": 0,
            "duration_s": 30.0,
        },
        {
            "arm": "control",
            "error": "void (exit=0, 0 files)",
            "hallucinated_refs": 0,
            "unnecessary_files": 0,
            "false_completion": 0,
            "duration_s": 3.0,
        },
        {
            "arm": "control",
            "error": "timeout",
            "hallucinated_refs": 0,
            "unnecessary_files": 0,
            "false_completion": 0,
            "duration_s": 300.0,
        },
    ]
    summary = runner.summarize(rows)["control"]
    assert (summary["runs"], summary["errors"], summary["void"]) == (1, 2, 1)


@pytest.fixture
def small_repo(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "__init__.py").write_text("")
    (root / "pkg" / "models.py").write_text(
        textwrap.dedent("""
        class Account:
            def __init__(self, owner):
                self.owner = owner
                self.balance = 0

            def deposit(self, amount):
                self.balance += amount
                return self.balance

            def summary(self):
                return f"{self.owner}: {self.balance}"
    """)
    )
    (root / "pkg" / "service.py").write_text(
        textwrap.dedent("""
        from pkg.models import Account


        def open_account(owner):
            account = Account(owner)
            account.deposit(10)
            return Account.summary(account)
    """)
    )
    (root / "requirements.txt").write_text("")
    return root


def test_precision_is_measured_on_claims_never_vacuously(small_repo):
    index = RepoIndex(small_repo).build()
    result = mutation.evaluate(index, mutation.generate(index, limit=50, per_file=5))
    assert result.total > 0
    assert result.clean_claims > 0  # the replay checked something
    assert result.precision is not None
    assert result.false_positives == 0
    assert "attribute_on_self" in result.by_kind
    assert "fresh-file replay" in mutation.render(result)


def test_precision_over_nothing_is_not_reported():
    empty = mutation.Result(missed=[])
    assert empty.precision is None
    assert "not measured" in mutation.render(empty)


def test_sample_is_seeded_and_capped_per_file(small_repo):
    index = RepoIndex(small_repo).build()
    capped = mutation.generate(index, limit=100, per_file=1)
    assert len({m.path for m in capped}) == len(capped)
    assert [m.subject for m in mutation.generate(index, seed=3)] == [
        m.subject for m in mutation.generate(index, seed=3)
    ]


def test_replay_path_stays_in_the_same_package():
    assert mutation.replay_path("src/pkg/models.py") == "src/pkg/_agb_replay_models.py"
