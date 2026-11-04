"""G2b: timeline refinements — comment-only edits, reverts, narrowed runs, failing ids.

G2a made verification a timeline. Four refinements, each a false block or a miss in it:

* a comment-only edit after a pass made the pass "stale" (all three local stale claims D1
  inspected were 0-code-line edits) — Python files now carry an AST fingerprint;
* an edit and its revert still counted as a change (Pebble ``unstage``) — a file whose
  bytes are back to how the task found them is no change;
* a passing run of *unrelated* test files verified everything (D1 scenario C) — a run
  with test paths now verifies only what those paths cover;
* a full-suite failure was never closed by a narrower re-run, even of exactly the tests
  it named — a failure whose output named every failing test is closed once later passes
  re-ran each of them, and only then.

Driven through Claude-Code-shaped PreToolUse/PostToolUse payloads (the baseline is taken
at the PreToolUse), the real adapter and the real Guard, over a copy of `pyrepo`, where
`src/shop/utils/pagination.py` is covered by `tests/test_pagination.py` and
`src/shop/repositories/user.py` by `tests/test_user_repository.py`.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from tests.test_gate_timeline import PASS, Session, _last_findings
from truthstone.verify import runners

FIXTURES = Path(__file__).parent / "fixtures"
COVERED = "src/shop/utils/pagination.py"
CODE = "\n\ndef page_count(total, per_page):\n    return (total + per_page - 1) // per_page\n"
FAIL_NAMED = (
    "F.\n=== FAILURES ===\nE   assert 0 == 1\n"
    "=== short test summary info ===\n"
    "FAILED tests/test_pagination.py::test_paginate - assert 0 == 1\n"
    "=== 1 failed, 1 passed in 0.12s ===\n"
)


class TaskSession(Session):
    def change(self, path: str, content: str | None) -> None:
        """PreToolUse (the baseline is taken here), the write, then PostToolUse.
        ``None`` removes the file."""
        full = self.repo / path
        pre = {
            "session_id": "sess-1",
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": str(full), "content": content or ""},
        }
        self.send(pre)
        if content is None:
            full.unlink()
        else:
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(content)
        self.send({**pre, "hook_event_name": "PostToolUse", "tool_response": {"filePath": str(full)}})

    def original(self, path: str = COVERED) -> str:
        return (FIXTURES / "pyrepo" / path).read_text()


@pytest.fixture
def session(tmp_path):
    repo = tmp_path / "pyrepo"
    shutil.copytree(FIXTURES / "pyrepo", repo)
    s = TaskSession(repo)
    yield s
    s.close()


def _blocked(response: dict, kind: str) -> bool:
    return response.get("decision") == "block" and kind in response.get("reason", "")


# -- a comment-only edit keeps a pass ------------------------------------------------------------


def test_comment_only_edit_keeps_pass(session):
    session.prompt()
    session.change(COVERED, session.original() + CODE)
    session.run("pytest -q", PASS)
    session.change(COVERED, session.original() + CODE + "\n# Pages are 1-based; page 0 is page 1.\n")
    assert session.stop("Done, the tests pass.") == {}


def test_a_code_edit_after_the_pass_is_still_stale(session):
    session.prompt()
    session.change(COVERED, session.original() + CODE)
    session.run("pytest -q", PASS)
    session.change(COVERED, session.original() + CODE.replace("- 1", "- 2"))
    held = session.stop("Done.")
    assert _blocked(held, "changed after the last passing test run")
    assert "stale-verification" in _last_findings(session)


def test_a_docstring_is_code_it_can_be_a_doctest(session):
    session.prompt()
    session.change(COVERED, session.original() + CODE)
    session.run("pytest -q", PASS)
    session.change(
        COVERED, session.original() + CODE.replace(":\n    return", ':\n    """>>> 1"""\n    return')
    )
    assert _blocked(session.stop("Done."), "changed after the last passing test run")


def test_a_comment_in_a_file_first_changed_after_the_pass(session):
    """The pass ran on the file as the task found it: its baseline is the comparison."""
    session.prompt()
    session.change(COVERED, session.original() + CODE)
    session.run("pytest -q", PASS)
    models = "src/shop/models.py"
    session.change(models, session.original(models) + "\n# Limits live here.\n")
    assert session.stop("Done.") == {}
    session.change(models, session.original(models) + "\nEXTRA = 1\n")
    assert _blocked(session.stop("Done."), "src/shop/models.py changed after the last passing test run")


# -- a revert is no change -----------------------------------------------------------------------


def test_revert_is_no_change(session):
    session.prompt()
    session.change(COVERED, session.original() + CODE)
    session.change(COVERED, session.original())
    assert session.stop("Reverted; nothing to change after all.") == {}


def test_a_file_created_and_removed_again_is_no_change(session):
    session.prompt("Add a helper module.")
    session.change("src/shop/utils/scratch.py", "def helper(:\n")  # does not even parse
    session.change("src/shop/utils/scratch.py", None)
    assert session.stop("Done.") == {}


def test_the_baseline_is_the_file_as_the_task_found_it_not_git_head(session):
    """The developer's own uncommitted edit is not the agent's to have "reverted": putting
    the committed version back is a change."""
    developer = session.original() + "\n# developer's work in progress\nWIP = True\n"
    (session.repo / COVERED).write_text(developer)
    session.prompt()
    session.change(COVERED, session.original() + CODE)
    session.change(COVERED, session.original())
    held = session.stop("Done.")
    assert _blocked(held, "no tests were run")
    session.change(COVERED, developer)  # back to how the task found it
    assert session.stop("Done.") == {}


# -- a narrowed run verifies only its scope ------------------------------------------------------


def test_narrowed_run_does_not_verify_unrelated_change(session):
    """D1 scenario C: a passing run of an unrelated test file, filtered to nothing."""
    session.prompt()
    session.change(COVERED, session.original() + CODE)
    session.run(
        "pytest -q tests/test_user_repository.py -k nothing_related", "1 passed, 1 deselected in 0.01s\n"
    )
    held = session.stop("Done - all tests pass.")
    assert _blocked(held, "did not include the tests that cover it")
    assert "tests/test_pagination.py" in held["reason"]
    assert "`pytest tests/test_pagination.py`" in held["reason"]
    assert "off-target-verification" in _last_findings(session)
    # The command Truthstone suggested is a narrowed run, and it verifies the change.
    session.run("pytest tests/test_pagination.py", "1 passed in 0.01s\n")
    assert session.stop("Done.") == {}


def test_a_node_id_in_the_covering_file_verifies_it(session):
    session.prompt()
    session.change(COVERED, session.original() + CODE)
    session.run("pytest tests/test_pagination.py::test_paginate -q", "1 passed in 0.01s\n")
    assert session.stop("Done.") == {}


def test_a_path_relative_to_another_folder_still_counts(session):
    session.prompt()
    session.change(COVERED, session.original() + CODE)
    session.run("cd tests && pytest test_pagination.py", "1 passed in 0.01s\n")
    assert session.stop("Done.") == {}


@pytest.mark.parametrize(
    "command",
    [
        "pytest -k paginate",  # a filter alone: which tests it selected cannot be told
        "pytest tests/integration/test_flow.py",  # a path the index does not know
        "pytest 'tests/test_*.py'",  # a glob
        "make test",  # a runner whose arguments are not paths
    ],
)
def test_what_cannot_be_told_is_never_held(session, command):
    session.prompt()
    session.change(COVERED, session.original() + CODE)
    session.run(command, PASS)
    assert session.stop("Done.") == {}


def test_a_dependency_change_is_reached_through_its_importers_tests(session):
    """models.py has no test of its own; tests of the modules importing it reach it."""
    session.prompt()
    models = "src/shop/models.py"
    session.change(models, session.original(models) + "\nEXTRA = 1\n")
    session.run("pytest tests/test_user_repository.py", "1 passed in 0.01s\n")
    assert session.stop("Done.") == {}


# -- failing test ids ----------------------------------------------------------------------------


def test_fail_full_then_pass_unrelated_subset_blocks(session):
    session.prompt()
    session.change(COVERED, session.original() + CODE)
    session.run("pytest", FAIL_NAMED, exit_code=1)
    session.change(COVERED, session.original() + CODE + "\nFIXED = True\n")
    session.run("pytest tests/test_user_repository.py", "1 passed in 0.01s\n")
    held = session.stop("Fixed.")
    assert _blocked(held, "Re-run `pytest`")
    assert "narrower-verification" in _last_findings(session)


def test_failing_id_clears_only_when_covered(session):
    session.prompt()
    session.change(COVERED, session.original() + CODE)
    session.run("pytest", FAIL_NAMED, exit_code=1)
    session.change(COVERED, session.original() + CODE + "\nFIXED = True\n")
    session.run("pytest tests/test_user_repository.py", "1 passed in 0.01s\n")
    assert _blocked(session.stop("Fixed."), "Re-run `pytest`")
    # Now the one test the failure named, by its node id: the failure is closed.
    session.run("pytest tests/test_pagination.py::test_paginate", "1 passed in 0.01s\n")
    assert session.stop("Fixed.") == {}


def test_a_failure_that_named_only_some_of_its_tests_stays_open(session):
    """ "2 failed" with one FAILED line: the other failure is unknown, so a re-run of the
    named test does not close it."""
    session.prompt()
    session.change(COVERED, session.original() + CODE)
    two = FAIL_NAMED.replace("1 failed, 1 passed", "2 failed")
    session.run("pytest", two, exit_code=1)
    session.change(COVERED, session.original() + CODE + "\nFIXED = True\n")
    session.run("pytest tests/test_pagination.py::test_paginate", "1 passed in 0.01s\n")
    assert _blocked(session.stop("Fixed."), "Re-run `pytest`")


def test_a_filtered_rerun_does_not_clear_failing_ids(session):
    session.prompt()
    session.change(COVERED, session.original() + CODE)
    session.run("pytest", FAIL_NAMED, exit_code=1)
    session.run("pytest -k test_paginate", "1 passed, 1 deselected in 0.01s\n")
    assert _blocked(session.stop("Fixed."), "Re-run `pytest`")


# -- the pieces ----------------------------------------------------------------------------------


def _ran(command: str) -> runners.TestOutcome:
    outcome = runners.parse_output(command, PASS)
    outcome.seq = 1
    return outcome


def _known(*paths: str):
    def known(target: str, style: str) -> bool:
        if style == "pattern":
            return any(target in path for path in paths)
        names = {path.removesuffix(".py") if style == "module" else path for path in paths}
        return any(
            name == target or name.startswith(target + "/") or name.endswith("/" + target) for name in names
        )

    return known


@pytest.mark.parametrize(
    ("command", "covering", "reached"),
    [
        ("npx jest utils", {"web/src/utils.test.ts"}, True),  # jest positionals are path patterns
        ("npx jest api", {"web/src/utils.test.ts"}, False),
        ("python -m unittest tests.test_pagination", {"tests/test_pagination.py"}, True),
        ("python -m unittest tests.test_pagination.PageTest.test_zero", {"tests/test_pagination.py"}, True),
        ("python -m unittest tests.test_user_repository", {"tests/test_pagination.py"}, False),
        ("go test ./pkg/pages/...", {"pkg/pages/sub/page_test.go"}, True),
        ("go test ./pkg/users", {"pkg/pages/page_test.go"}, False),
        ("rspec spec/pages_spec.rb:12", {"spec/pages_spec.rb"}, True),
        ("pytest tests/", {"tests/test_pagination.py"}, True),  # the suite folder is the suite
        ("pytest tests/unit", {"tests/unit/test_pagination.py"}, True),
        ("pytest tests/unit", {"tests/api/test_pagination.py"}, False),
    ],
)
def test_run_reaches(command, covering, reached):
    known = _known(
        "web/src/utils.test.ts",
        "web/src/api.test.ts",
        "tests/test_pagination.py",
        "tests/test_user_repository.py",
        "pkg/pages/sub/page_test.go",
        "pkg/users/user_test.go",
        "pkg/pages/page_test.go",
        "spec/pages_spec.rb",
        "tests/unit/test_pagination.py",
        "tests/api/test_pagination.py",
    )
    assert runners.run_reaches(_ran(command), "src/x", covering, known) is reached


def test_failing_tests_are_read_from_pytests_own_lines():
    from truthstone.verify import parsers

    text = (
        "FAILED tests/test_a.py::test_x[1-2] - AssertionError: no\n"
        "ERROR tests/test_b.py - ImportError: nope\n"
        "tests/test_c.py::TestC::test_y FAILED\n"
        "FAILED isn't a pytest line here\n"
    )
    assert parsers.failing_tests(text) == (
        "tests/test_a.py::test_x[1-2]",
        "tests/test_b.py",
        "tests/test_c.py::TestC::test_y",
    )


def test_a_parametrized_id_is_inside_its_function():
    later, earlier = _ran("pytest tests/test_a.py::test_x"), _ran("pytest tests/test_a.py::test_x[1]")
    assert runners.covers(later, earlier)
