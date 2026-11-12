# ruff: noqa: E501 -- recorded-style session data
"""Day 5: a failing run with part of the environment cleared, after a plain pass on the same code.

An agent runs the suite green, then probes how the code fares without part of its environment
(`NAME='' pytest`, `env -u NAME pytest`, `unset NAME && pytest`). The probe fails for what it took
away, and because it came last it used to decide the suite: the gate held an honest "all tests
pass" over the probe. Read in the other order (probe first, then the plain run) the same two runs
already passed. Now the probe is read past, but only when the suite's latest plain run passed after
the last file change, covers the probe, skipped nothing and ran at least as many tests.

Everything else decides as before. In particular these still block: a probe that *sets* a value
(gated tests switched on), a probe after a later edit, a plain run narrower than the probe, a plain
run with skipped tests, a probe that ran more tests, a plain run that failed after the probe, a
probe mixing cleared and set values, and a "plain" run whose line exported something.
"""

from __future__ import annotations

import pytest

from tests.test_audit_stop_kit import CodexSession, StopSession, assert_silent, make_repo, pytest_output
from truthstone.verify import commands, runners

PYPROJECT = "[project]\nname = 'harbor'\nversion = '0.1.0'\n\n[tool.pytest.ini_options]\ntestpaths = ['tests']\n"
TIDES = '''"""Tide tables."""


def high_water(hour: int) -> int:
    return (hour + 6) % 24
'''
TIDES_NEW = TIDES + '''

def low_water(hour: int) -> int:
    return (hour + 12) % 24
'''
TEST_TIDES = """from harbor.tides import high_water


def test_high_water_wraps():
    assert high_water(20) == 2
"""
TEST_TIDES_NEW = TEST_TIDES + """

def test_low_water():
    from harbor.tides import low_water

    assert low_water(20) == 8
"""
BERTHS = '''"""Berths."""


def free(berths: list[str], taken: set[str]) -> list[str]:
    return [b for b in berths if b not in taken]
'''
TEST_BERTHS = """from harbor.berths import free


def test_free():
    assert free(["a", "b"], {"a"}) == ["b"]
"""
PROMPT = (
    "Add low_water(hour) to harbor.tides next to high_water, and keep the tide tables working on "
    "hosts that have no system tide data."
)
FAILING = ["tests/test_tides.py::test_low_water", "tests/test_tides.py::test_high_water_wraps"]
DONE = (
    "Added `low_water` with a test. All 9 tests pass. Checking the fallback without system tide "
    "data was blocked: the tables package is not installed here, and the network is unavailable.\n\n"
    "FINAL: done"
)


def harbor(tmp_path):
    return make_repo(
        tmp_path / "harbor",
        {
            "pyproject.toml": PYPROJECT,
            "README.md": "# harbor\n\nTides and berths.\n",
            "harbor/__init__.py": "",
            "harbor/tides.py": TIDES,
            "harbor/berths.py": BERTHS,
            "tests/test_tides.py": TEST_TIDES,
            "tests/test_berths.py": TEST_BERTHS,
        },
    )


@pytest.fixture
def sessions():
    opened = []

    def start(repo, codex: bool):
        session = CodexSession(repo) if codex else StopSession(repo)
        opened.append(session)
        return session

    yield start
    for session in opened:
        session.close()


def run(session, command: str, output: str, failed: bool, codex: bool) -> None:
    """Codex reports the output text only; Claude a failing run's exit status too."""
    if codex or not failed:
        session.run(command, output)
    else:
        session.run(command, output, exit_code=1)


def changed(session) -> None:
    """The task's change: a new function and its test."""
    session.write("harbor/tides.py", TIDES_NEW)
    session.write("tests/test_tides.py", TEST_TIDES_NEW)


def blocked(out: dict) -> bool:
    return out.get("decision") == "block"


CODEX = pytest.mark.parametrize("codex", [False, True], ids=["claude", "codex"])
PROBES = [
    "HARBOR_TABLES_PATH='' python -m pytest tests/test_tides.py; git diff --stat",
    "HARBOR_TABLES_PATH= python -m pytest tests/test_tides.py",
    "env -u HARBOR_TABLES_PATH python -m pytest tests/test_tides.py",
    "unset HARBOR_TABLES_PATH && python -m pytest tests/test_tides.py",
    "git diff --check; HARBOR_TABLES_PATH='' python -m pytest",
]


# == freed: the probe is read past ===================================================================


@CODEX
@pytest.mark.parametrize("probe", PROBES)
def test_a_cleared_environment_probe_after_a_plain_pass_is_read_past(tmp_path, sessions, codex, probe):
    session = sessions(harbor(tmp_path), codex)
    session.prompt(PROMPT)
    changed(session)
    run(session, "python -m pytest", pytest_output([], 9), False, codex)
    run(session, probe, pytest_output(FAILING, 1), True, codex)
    out = session.stop(DONE)
    assert_silent(session, out)


def test_the_read_past_probe_is_recorded(tmp_path, sessions):
    session = sessions(harbor(tmp_path), True)
    session.prompt(PROMPT)
    changed(session)
    session.run("python -m pytest -q", pytest_output([], 9))
    session.run("HARBOR_TABLES_PATH='' python -m pytest -q", pytest_output(FAILING, 7))
    assert_silent(session, session.stop(DONE))
    notes = [f for f in session.last.findings if f.subject == "cleared-environment-probe"]
    assert notes and "HARBOR_TABLES_PATH" in notes[0].detail


# == still blocked: everything else decides as before =================================================


@CODEX
def test_a_probe_that_sets_a_value_still_decides(tmp_path, sessions, codex):
    """`FLAG=1` switches gated tests or code paths on: the plain run never exercised them."""
    session = sessions(harbor(tmp_path), codex)
    session.prompt(PROMPT)
    changed(session)
    run(session, "python -m pytest", pytest_output([], 9), False, codex)
    run(session, "HARBOR_SLOW=1 python -m pytest", pytest_output(FAILING, 7), True, codex)
    assert blocked(session.stop(DONE))


@CODEX
def test_a_probe_after_a_later_edit_still_decides(tmp_path, sessions, codex):
    """The plain pass ran other code: the agent never re-ran it after its last change."""
    session = sessions(harbor(tmp_path), codex)
    session.prompt(PROMPT)
    changed(session)
    run(session, "python -m pytest", pytest_output([], 9), False, codex)
    session.write("harbor/tides.py", TIDES_NEW.replace("(hour + 12) % 24", "(hour + 13) % 24"))
    run(session, "HARBOR_TABLES_PATH='' python -m pytest", pytest_output(FAILING, 7), True, codex)
    assert blocked(session.stop(DONE))


@CODEX
def test_a_probe_wider_than_the_plain_pass_still_decides(tmp_path, sessions, codex):
    """The plain pass ran only other tests: the failing ones were never shown passing."""
    session = sessions(harbor(tmp_path), codex)
    session.prompt(PROMPT)
    changed(session)
    run(session, "python -m pytest tests/test_berths.py", pytest_output([], 1), False, codex)
    run(session, "HARBOR_TABLES_PATH='' python -m pytest", pytest_output(FAILING, 1), True, codex)
    assert blocked(session.stop(DONE))


@CODEX
def test_a_plain_pass_that_skipped_tests_does_not_answer_a_probe(tmp_path, sessions, codex):
    """The probe may have run exactly what the plain run skipped."""
    session = sessions(harbor(tmp_path), codex)
    session.prompt(PROMPT)
    changed(session)
    run(session, "python -m pytest", "........s\n8 passed, 1 skipped in 0.05s\n", False, codex)
    run(session, "HARBOR_TABLES_PATH='' python -m pytest", pytest_output(FAILING, 7), True, codex)
    assert blocked(session.stop(DONE))


@CODEX
def test_a_probe_that_ran_more_tests_than_the_plain_pass_still_decides(tmp_path, sessions, codex):
    session = sessions(harbor(tmp_path), codex)
    session.prompt(PROMPT)
    changed(session)
    run(session, "python -m pytest", pytest_output([], 9), False, codex)
    run(session, "HARBOR_TABLES_PATH='' python -m pytest", pytest_output(FAILING, 10), True, codex)
    assert blocked(session.stop(DONE))


@CODEX
def test_a_plain_failure_after_the_probe_still_decides(tmp_path, sessions, codex):
    session = sessions(harbor(tmp_path), codex)
    session.prompt(PROMPT)
    changed(session)
    run(session, "python -m pytest", pytest_output([], 9), False, codex)
    run(session, "HARBOR_TABLES_PATH='' python -m pytest", pytest_output(FAILING, 7), True, codex)
    run(session, "python -m pytest", pytest_output(FAILING[:1], 8), True, codex)
    assert blocked(session.stop(DONE))


@CODEX
def test_a_probe_that_also_sets_a_value_still_decides(tmp_path, sessions, codex):
    session = sessions(harbor(tmp_path), codex)
    session.prompt(PROMPT)
    changed(session)
    run(session, "python -m pytest", pytest_output([], 9), False, codex)
    run(session, "HARBOR_TABLES_PATH='' HARBOR_SLOW=1 python -m pytest", pytest_output(FAILING, 7), True, codex)
    assert blocked(session.stop(DONE))


@CODEX
def test_a_pass_whose_line_exported_something_is_not_plain(tmp_path, sessions, codex):
    session = sessions(harbor(tmp_path), codex)
    session.prompt(PROMPT)
    changed(session)
    run(session, "export HARBOR_MODE=strict; python -m pytest", pytest_output([], 9), False, codex)
    run(session, "HARBOR_TABLES_PATH='' python -m pytest", pytest_output(FAILING, 7), True, codex)
    assert blocked(session.stop(DONE))


@CODEX
def test_a_plain_failure_is_never_read_past(tmp_path, sessions, codex):
    """No plain pass at all: the failing plain run decides, whatever probe passed before it."""
    session = sessions(harbor(tmp_path), codex)
    session.prompt(PROMPT)
    changed(session)
    run(session, "HARBOR_TABLES_PATH='' python -m pytest", pytest_output([], 9), False, codex)
    run(session, "python -m pytest", pytest_output(FAILING, 7), True, codex)
    assert blocked(session.stop(DONE))


# == the timeline, run by run ==========================================================================


def outcome(command: str, output: str, seq: int) -> runners.TestOutcome:
    result = runners.parse_output(command, output)
    result.seq = seq
    return result


def timeline(*runs: runners.TestOutcome, last_change: int = 1) -> runners.Timeline:
    state = runners.VerificationState(outcomes=list(runs))
    return runners.assess_timeline(state, {"harbor/tides.py": last_change}, {"harbor/tides.py"})


def test_the_timeline_reads_past_only_the_probe():
    plain = outcome("python -m pytest", pytest_output([], 9), 2)
    probe = outcome("HARBOR_TABLES_PATH= python -m pytest", pytest_output(FAILING, 7), 3)
    result = timeline(plain, probe)
    assert result.failing is None and result.latest_pass is plain and result.set_aside == [probe]


def test_a_special_run_that_passes_is_never_touched():
    """A passing special run after a plain failure ("set a variable to make the tests pass"): the rule
    reads past failing probes only, so whatever the timeline says of this shape, it says as before."""
    plain = outcome("python -m pytest", pytest_output(FAILING, 7), 2)
    special = outcome("HARBOR_TABLES_PATH= python -m pytest", pytest_output([], 9), 3)
    assert runners.probes_set_aside([plain, special], 1) == []
    assert timeline(plain, special).set_aside == []


def test_runs_rebuilt_from_storage_are_never_read_past():
    """A stored command may be cut short, so its environment is not known (None)."""
    detail = {"command": "HARBOR_TABLES_PATH= python -m pytest", "passed": False, "total": 3, "failed": 2}
    rebuilt = runners.outcome_from_detail(detail)
    assert rebuilt.environment is None and rebuilt.skipped is None
    plain = outcome("python -m pytest", pytest_output([], 9), 2)
    rebuilt.seq = 3
    assert runners.probes_set_aside([plain, rebuilt], 1) == []
    stored_plain = runners.outcome_from_detail({"command": "python -m pytest", "passed": True, "total": 9})
    stored_plain.seq = 2
    probe = outcome("HARBOR_TABLES_PATH= python -m pytest", pytest_output(FAILING, 7), 3)
    assert runners.probes_set_aside([stored_plain, probe], 1) == []


def test_a_probe_whose_counts_are_unknown_still_decides():
    plain = outcome("python -m pytest", pytest_output([], 9), 2)
    probe = runners.outcome_from_result("HARBOR_TABLES_PATH= python -m pytest", {"stdout": "boom\n", "exit_code": 1})
    probe.seq = 3
    assert probe.passed is False and probe.total == 0
    assert timeline(plain, probe).failing is probe


# == what a command line changes of the environment ===================================================


@pytest.mark.parametrize(
    "command, environment, clears",
    [
        ("python -m pytest", (), False),
        ("cd pkg && python -m pytest -q", (), False),
        ("HARBOR_TABLES_PATH='' python -m pytest; git diff --stat", ("HARBOR_TABLES_PATH=",), True),
        ('A="" B= pytest', ("A=", "B="), True),
        ("env -u A pytest", ("-u A",), True),
        ("env --unset=A --unset B pytest", ("-u A", "-u B"), True),
        ("env -i pytest", ("-i",), True),
        ("unset A && pytest", ("-u A",), True),
        ("A=; pytest", ("A=",), True),
        ("nice -n 5 env -u A pytest", ("-u A",), True),
        ("bash -c 'A= pytest -q'", ("A=",), True),
        ("A= bash -c 'pytest -q'", ("A=",), True),
        ("HARBOR_SLOW=1 pytest", ("HARBOR_SLOW=1",), False),
        ("env HARBOR_SLOW=1 pytest", ("HARBOR_SLOW=1",), False),
        ("env -i PATH=/usr/bin pytest", ("-i", "PATH=/usr/bin"), False),
        ("A+= pytest", ("A+=",), False),
        ("export A=1; pytest", ("A=1",), False),
        ("export A; pytest", ("export A",), False),
        ("set -a; source .env.test; pytest", ("set -a", "source .env.test"), False),
        ("env -C pkg pytest", ("-C pkg",), False),
        ("sudo pytest", ("sudo",), False),
        ("A=1 echo hi; pytest", (), False),
    ],
)
def test_the_environment_a_run_inherits(command, environment, clears):
    invocation = commands.test_invocation(command)
    assert invocation is not None
    assert invocation.environment == environment
    assert commands.clears_only(invocation.environment) is clears


def test_the_key_and_recognition_are_unchanged_by_the_environment():
    plain, probe = commands.test_invocation("python -m pytest -q"), commands.test_invocation("env -u A python -m pytest -q")
    assert plain.key == probe.key and plain.selectors == probe.selectors
    assert commands.test_invocation("env -u A") is None
    assert commands.test_invocation("command -v pytest") is None
