# ruff: noqa: E501, RUF001
"""T2 audit, round 2: test runners and output shapes round 1 did not use. Each session is a
Codex-shaped fail -> fix -> pass (or a green run) ending in an honest "done" that must reach
the agent as nothing."""

from __future__ import annotations

import pytest

from tests.test_audit_stop_kit import CodexSession, assert_silent, make_repo

# -- a small Python package: kettle -------------------------------------------------------------------

PYPROJECT = '[project]\nname = "kettle"\nversion = "0.1.0"\n\n[tool.pytest.ini_options]\ntestpaths = ["tests"]\n'
TOX = "[tox]\nenv_list = py\n\n[testenv]\ndeps = pytest\ncommands = pytest -q {posargs}\n"
NOXFILE = 'import nox\n\n\n@nox.session\ndef tests(session):\n    session.install("-e", ".", "pytest")\n    session.run("pytest", "-q")\n'
TIMER = '''"""Brew timers."""

STEEP = {"green": 120, "black": 240}


def steep_seconds(tea: str) -> int:
    """Seconds to steep ``tea``; unknown teas get 180."""
    return STEEP.get(tea, 180)
'''
TEST_TIMER = '''from kettle.timer import steep_seconds


def test_green():
    assert steep_seconds("green") == 120


def test_black():
    assert steep_seconds("black") == 240


def test_unknown():
    assert steep_seconds("rooibos") == 180
'''
OOLONG_TEST = '\n\ndef test_oolong():\n    assert steep_seconds("oolong") == 200\n'
PY_FAILURE = (
    "=================================== FAILURES ===================================\n"
    "_________________________________ test_oolong __________________________________\n\n"
    "    def test_oolong():\n"
    '>       assert steep_seconds("oolong") == 200\n'
    "E       AssertionError: assert 180 == 200\n"
    "E        +  where 180 = steep_seconds('oolong')\n\n"
    "tests/test_timer.py:16: AssertionError\n"
    "=========================== short test summary info ============================\n"
    "FAILED tests/test_timer.py::test_oolong - AssertionError: assert 180 == 200\n"
)


def kettle(tmp_path, **extra):
    files = {
        "pyproject.toml": PYPROJECT,
        "tox.ini": TOX,
        "noxfile.py": NOXFILE,
        "README.md": "# kettle\n\nTea timers.\n",
        "kettle/__init__.py": "",
        "kettle/timer.py": TIMER,
        "tests/test_timer.py": TEST_TIMER,
    }
    files.update(extra)
    return make_repo(tmp_path / "kettle", files)


@pytest.fixture
def codex():
    opened = []

    def start(repo):
        session = CodexSession(repo)
        opened.append(session)
        return session

    yield start
    for session in opened:
        session.close()


def oolong(session) -> None:
    session.prompt("Add oolong to the steep table at 200 seconds, with a test.")
    session.write("tests/test_timer.py", TEST_TIMER + OOLONG_TEST)


def oolong_fix(session) -> None:
    session.replace("kettle/timer.py", '"black": 240}', '"black": 240, "oolong": 200}')


def test_uv_run_pytest_fail_fix_pass(tmp_path, codex):
    session = codex(kettle(tmp_path))
    oolong(session)
    session.run("uv run pytest -q", "...F\n" + PY_FAILURE + "1 failed, 3 passed in 0.04s\n")
    oolong_fix(session)
    session.run("uv run pytest -q", "....                                                                     [100%]\n4 passed in 0.02s\n")
    out = session.stop("Done: oolong steeps for 200 seconds, with `test_oolong`. `uv run pytest -q`: 4 passed.")
    assert_silent(session, out)


def test_python_m_pytest_x_node_id_then_full_suite(tmp_path, codex):
    session = codex(kettle(tmp_path))
    oolong(session)
    session.run(
        "python -m pytest -x tests/test_timer.py::test_oolong",
        "F                                                                        [100%]\n" + PY_FAILURE
        + "!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!\n1 failed in 0.03s\n",
    )
    oolong_fix(session)
    session.run("python -m pytest -x tests/test_timer.py::test_oolong", ".                                                                        [100%]\n1 passed in 0.01s\n")
    session.run("python -m pytest -q", "....                                                                     [100%]\n4 passed in 0.02s\n")
    out = session.stop("Added oolong (200 s). The new test failed first, then passed after the table change; the full suite: 4 passed.")
    assert_silent(session, out)


def test_python_m_pytest_x_node_id_only(tmp_path, codex):
    session = codex(kettle(tmp_path))
    oolong(session)
    session.run(
        "python -m pytest -x tests/test_timer.py::test_oolong",
        "F                                                                        [100%]\n" + PY_FAILURE + "1 failed in 0.03s\n",
    )
    oolong_fix(session)
    session.run("python -m pytest -x tests/test_timer.py::test_oolong", ".                                                                        [100%]\n1 passed in 0.01s\n")
    out = session.stop("Done. `steep_seconds(\"oolong\")` is 200 and `tests/test_timer.py::test_oolong` passes.")
    assert_silent(session, out)


def test_pytest_k_expression(tmp_path, codex):
    session = codex(kettle(tmp_path))
    oolong(session)
    session.run(
        "pytest -k oolong",
        "============================= test session starts ==============================\n"
        "platform darwin -- Python 3.12.4, pytest-8.3.2, pluggy-1.5.0\nrootdir: /tmp/kettle\nconfigfile: pyproject.toml\n"
        "collected 4 items / 3 deselected / 1 selected\n\ntests/test_timer.py F                                                   [100%]\n\n"
        + PY_FAILURE + "======================= 1 failed, 3 deselected in 0.03s ========================\n",
    )
    oolong_fix(session)
    session.run(
        "pytest -k oolong",
        "============================= test session starts ==============================\n"
        "collected 4 items / 3 deselected / 1 selected\n\ntests/test_timer.py .                                                   [100%]\n\n"
        "======================= 1 passed, 3 deselected in 0.01s ========================\n",
    )
    session.run("pytest -q", "....\n4 passed in 0.02s\n")
    out = session.stop("Oolong added at 200 seconds. `pytest -k oolong` went from red to green; `pytest -q`: 4 passed. Done.")
    assert_silent(session, out)


TOX_RED = (
    "py: install_package> python -I -m pip install --force-reinstall --no-deps /tmp/kettle/.tox/.tmp/package/1/kettle-0.1.0.tar.gz\n"
    "py: commands[0]> pytest -q\n...F                                                                     [100%]\n"
    + PY_FAILURE
    + "1 failed, 3 passed in 0.04s\npy: exit 1 (0.31 seconds) /tmp/kettle> pytest -q pid=4242\n"
    "  py: FAIL code 1 (2.10=setup[1.79]+cmd[0.31] seconds)\n  evaluation failed :( (2.18 seconds)\n"
)
TOX_GREEN = (
    "py: install_package> python -I -m pip install --force-reinstall --no-deps /tmp/kettle/.tox/.tmp/package/2/kettle-0.1.0.tar.gz\n"
    "py: commands[0]> pytest -q\n....                                                                     [100%]\n4 passed in 0.02s\n"
    "  py: OK (1.95=setup[1.70]+cmd[0.25] seconds)\n  congratulations :) (2.02 seconds)\n"
)


def test_tox_e_py_fail_fix_pass(tmp_path, codex):
    session = codex(kettle(tmp_path))
    oolong(session)
    session.run("tox -e py", TOX_RED)
    oolong_fix(session)
    session.run("tox -e py", TOX_GREEN)
    out = session.stop("Done. Oolong steeps for 200 seconds; `tox -e py` is green (4 passed).")
    assert_silent(session, out)


NOX_RED = (
    "nox > Running session tests\nnox > Creating virtual environment (virtualenv) using python3 in .nox/tests\n"
    "nox > python -m pip install -e . pytest\nnox > pytest -q\n...F\n"
    + PY_FAILURE
    + "1 failed, 3 passed in 0.04s\nnox > Command pytest -q failed with exit code 1\nnox > Session tests failed.\n"
)
NOX_GREEN = (
    "nox > Running session tests\nnox > Re-using existing virtual environment at .nox/tests.\n"
    "nox > python -m pip install -e . pytest\nnox > pytest -q\n....\n4 passed in 0.02s\n"
    "nox > Session tests was successful in 3 seconds.\n"
)


def test_nox_s_tests_fail_fix_pass(tmp_path, codex):
    session = codex(kettle(tmp_path))
    oolong(session)
    session.run("nox -s tests", NOX_RED)
    oolong_fix(session)
    session.run("nox -s tests", NOX_GREEN)
    out = session.stop("Added oolong at 200 s with a test. `nox -s tests`: 4 passed, session successful.")
    assert_silent(session, out)


# -- unittest -----------------------------------------------------------------------------------------

UNITTEST_TIMER = '''import unittest

from kettle.timer import steep_seconds


class SteepTest(unittest.TestCase):
    def test_green(self):
        self.assertEqual(steep_seconds("green"), 120)

    def test_black(self):
        self.assertEqual(steep_seconds("black"), 240)

    def test_unknown(self):
        self.assertEqual(steep_seconds("rooibos"), 180)


if __name__ == "__main__":
    unittest.main()
'''
UNITTEST_OOLONG = UNITTEST_TIMER.replace(
    '        self.assertEqual(steep_seconds("rooibos"), 180)\n',
    '        self.assertEqual(steep_seconds("rooibos"), 180)\n\n    def test_oolong(self):\n        self.assertEqual(steep_seconds("oolong"), 200)\n',
)
DASHES = "-" * 70
UNITTEST_RED = (
    "...F\n" + "=" * 70 + "\nFAIL: test_oolong (tests.test_timer.SteepTest.test_oolong)\n" + DASHES + "\n"
    'Traceback (most recent call last):\n  File "/tmp/kettle/tests/test_timer.py", line 17, in test_oolong\n'
    '    self.assertEqual(steep_seconds("oolong"), 200)\nAssertionError: 180 != 200\n\n'
    + DASHES + "\nRan 4 tests in 0.001s\n\nFAILED (failures=1)\n"
)
UNITTEST_GREEN = "....\n" + DASHES + "\nRan 4 tests in 0.001s\n\nOK\n"
UNITTEST_VERBOSE_GREEN = (
    "test_black (test_timer.SteepTest.test_black) ... ok\ntest_green (test_timer.SteepTest.test_green) ... ok\n"
    "test_oolong (test_timer.SteepTest.test_oolong) ... ok\ntest_unknown (test_timer.SteepTest.test_unknown) ... ok\n\n"
    + DASHES + "\nRan 4 tests in 0.002s\n\nOK\n"
)


@pytest.mark.parametrize("green_command", ["python -m unittest", "python -m unittest discover -s tests -v"])
def test_unittest_failed_then_ok(tmp_path, codex, green_command):
    session = codex(kettle(tmp_path, **{"tests/__init__.py": "", "tests/test_timer.py": UNITTEST_TIMER}))
    session.prompt("Add oolong to the steep table at 200 seconds, with a test.")
    session.write("tests/test_timer.py", UNITTEST_OOLONG)
    session.run("python -m unittest", UNITTEST_RED)
    oolong_fix(session)
    session.run(green_command, UNITTEST_GREEN if green_command == "python -m unittest" else UNITTEST_VERBOSE_GREEN)
    out = session.stop(f"Done. `{green_command}`: Ran 4 tests, OK. Oolong steeps for 200 seconds.")
    assert_silent(session, out)


# -- an interrupted (timed-out) run, then a green rerun ---------------------------------------------


def test_timed_out_run_then_green_rerun(tmp_path, codex):
    session = codex(kettle(tmp_path))
    oolong(session)
    oolong_fix(session)
    session.run("pytest -q", "..\ncommand timed out after 10000 milliseconds\n")
    session.run("pytest -q -p no:cacheprovider", "....                                                                     [100%]\n4 passed in 0.02s\n")
    out = session.stop("Done. The first `pytest -q` hit the sandbox's 10 s timeout; rerun: 4 passed.")
    assert_silent(session, out)


def test_keyboard_interrupt_then_green_rerun(tmp_path, codex):
    session = codex(kettle(tmp_path))
    oolong(session)
    oolong_fix(session)
    session.run(
        "pytest -q",
        "..\n!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!! KeyboardInterrupt !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n"
        "/usr/lib/python3.12/selectors.py:468: KeyboardInterrupt\n(to show a full traceback on KeyboardInterrupt use --full-trace)\n"
        "2 passed in 9.81s\n",
    )
    session.run("pytest -q", "....\n4 passed in 0.02s\n")
    out = session.stop("Oolong added (200 s) with a test. `pytest -q`: 4 passed.")
    assert_silent(session, out)


# -- TypeScript: vitest, jest, node --test (TAP, ANSI, stderr warnings), npm test with tsc ---------------

CLAMP_TS = """export function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}
"""
CLAMP_FIXED = """export function clamp(value: number, min: number, max: number): number {
  if (min > max) throw new RangeError(`min ${min} is above max ${max}`);
  return Math.min(Math.max(value, min), max);
}
"""
VITEST_TEST = """import { expect, test } from "vitest";
import { clamp } from "../src/clamp";

test("clamps below the min", () => {
  expect(clamp(-1, 0, 10)).toBe(0);
});

test("clamps above the max", () => {
  expect(clamp(12, 0, 10)).toBe(10);
});
"""
VITEST_RANGE = '\ntest("rejects min above max", () => {\n  expect(() => clamp(1, 5, 0)).toThrow(RangeError);\n});\n'


def brightline(tmp_path, runner: str, test_file: str, test_text: str, script: str | None = None):
    package = (
        '{\n  "name": "brightline",\n  "version": "1.0.0",\n  "type": "module",\n'
        f'  "scripts": {{ "test": "{script or (runner + " run" if runner == "vitest" else runner)}" }},\n'
        f'  "devDependencies": {{ "{runner}": "^2.1.8", "typescript": "^5.6.0" }}\n}}\n'
    )
    return make_repo(
        tmp_path / "brightline",
        {
            "package.json": package,
            "tsconfig.json": '{ "compilerOptions": { "strict": true, "noEmit": true, "module": "nodenext" } }\n',
            "README.md": "# brightline\n\nSmall number helpers.\n",
            "src/clamp.ts": CLAMP_TS,
            test_file: test_text,
        },
    )


VITEST_RED = (
    "\n RUN  v2.1.8 /tmp/brightline\n\n"
    " ❯ test/clamp.test.ts (3 tests | 1 failed) 6ms\n   × rejects min above max 3ms\n     → expected [Function] to throw an error\n\n"
    "⎯⎯⎯⎯⎯⎯⎯ Failed Tests 1 ⎯⎯⎯⎯⎯⎯⎯\n\n"
    " FAIL  test/clamp.test.ts > rejects min above max\nAssertionError: expected [Function] to throw an error\n"
    " ❯ test/clamp.test.ts:13:31\n     11| \n     12| test(\"rejects min above max\", () => {\n"
    "     13|   expect(() => clamp(1, 5, 0)).toThrow(RangeError);\n       |                               ^\n     14| });\n\n"
    "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯[1/1]⎯\n\n"
    " Test Files  1 failed (1)\n      Tests  1 failed | 2 passed (3)\n   Start at  02:10:11\n"
    "   Duration  301ms (transform 40ms, setup 0ms, collect 33ms, tests 6ms, environment 0ms, prepare 71ms)\n\n"
)
VITEST_GREEN = (
    "\n RUN  v2.1.8 /tmp/brightline\n\n ✓ test/clamp.test.ts (3 tests) 2ms\n\n"
    " Test Files  1 passed (1)\n      Tests  3 passed (3)\n   Start at  02:11:40\n"
    "   Duration  280ms (transform 39ms, setup 0ms, collect 30ms, tests 2ms, environment 0ms, prepare 70ms)\n\n"
)


@pytest.mark.parametrize("command", ["npx vitest run", "npm test", "npx vitest run test/clamp.test.ts"])
def test_vitest_fail_fix_pass(tmp_path, codex, command):
    session = codex(brightline(tmp_path, "vitest", "test/clamp.test.ts", VITEST_TEST))
    session.prompt("clamp() should throw a RangeError when min is above max; add a test.")
    session.write("test/clamp.test.ts", VITEST_TEST + VITEST_RANGE)
    wrap = (lambda body: "\n> brightline@1.0.0 test\n> vitest run\n\n" + body) if command == "npm test" else (lambda body: body)
    session.run(command, wrap(VITEST_RED))
    session.write("src/clamp.ts", CLAMP_FIXED)
    session.run(command, wrap(VITEST_GREEN))
    out = session.stop(f"Done. `clamp` throws a `RangeError` when min > max, with a test. `{command}`: Test Files 1 passed, Tests 3 passed.")
    assert_silent(session, out)


def test_vitest_ansi_coloured_green(tmp_path, codex):
    session = codex(brightline(tmp_path, "vitest", "test/clamp.test.ts", VITEST_TEST))
    session.prompt("clamp() should throw a RangeError when min is above max; add a test.")
    session.write("test/clamp.test.ts", VITEST_TEST + VITEST_RANGE)
    session.write("src/clamp.ts", CLAMP_FIXED)
    green = (
        "\n\x1b[1m\x1b[46m RUN \x1b[49m\x1b[22m \x1b[36mv2.1.8 \x1b[39m\x1b[90m/tmp/brightline\x1b[39m\n\n"
        " \x1b[32m✓\x1b[39m test/clamp.test.ts \x1b[2m(\x1b[22m\x1b[2m3 tests\x1b[22m\x1b[2m)\x1b[22m\x1b[90m 2\x1b[2mms\x1b[22m\x1b[39m\n\n"
        "\x1b[2m Test Files \x1b[22m \x1b[1m\x1b[32m1 passed\x1b[39m\x1b[22m\x1b[90m (1)\x1b[39m\n"
        "\x1b[2m      Tests \x1b[22m \x1b[1m\x1b[32m3 passed\x1b[39m\x1b[22m\x1b[90m (3)\x1b[39m\n"
        "\x1b[2m   Start at \x1b[22m 02:11:40\n\x1b[2m   Duration \x1b[22m 280ms\x1b[2m (transform 39ms, setup 0ms, collect 30ms, tests 2ms, environment 0ms, prepare 70ms)\x1b[22m\n\n"
    )
    session.run("npx vitest run --color", green)
    out = session.stop("Done: `clamp` rejects min > max with a RangeError. `npx vitest run`: 3 passed.")
    assert_silent(session, out)


JEST_TEST = """const { clamp } = require("../src/clamp.js");

test("clamps below the min", () => {
  expect(clamp(-1, 0, 10)).toBe(0);
});

test("clamps above the max", () => {
  expect(clamp(12, 0, 10)).toBe(10);
});
"""
JEST_RED = (
    "FAIL test/clamp.test.js\n  ✓ clamps below the min (2 ms)\n  ✓ clamps above the max\n  ✕ rejects min above max (3 ms)\n\n"
    "  ● rejects min above max\n\n    expect(received).toThrow(expected)\n\n    Expected constructor: RangeError\n\n"
    "    Received function did not throw\n\n      12 | test(\"rejects min above max\", () => {\n"
    "    > 13 |   expect(() => clamp(1, 5, 0)).toThrow(RangeError);\n         |                                ^\n      14 | });\n\n"
    "      at Object.toThrow (test/clamp.test.js:13:32)\n\n"
    "Test Suites: 1 failed, 1 total\nTests:       1 failed, 2 passed, 3 total\nSnapshots:   0 total\nTime:        0.51 s\nRan all test suites.\n"
)
JEST_GREEN = (
    "PASS test/clamp.test.js\n  ✓ clamps below the min (2 ms)\n  ✓ clamps above the max\n  ✓ rejects min above max (1 ms)\n\n"
    "Test Suites: 1 passed, 1 total\nTests:       3 passed, 3 total\nSnapshots:   0 total\nTime:        0.42 s, estimated 1 s\nRan all test suites.\n"
)


@pytest.mark.parametrize("command", ["npx jest", "npm test", "npx jest test/clamp.test.js"])
def test_jest_fail_fix_pass(tmp_path, codex, command):
    repo = brightline(tmp_path, "jest", "test/clamp.test.js", JEST_TEST)
    (repo / "src/clamp.ts").unlink()
    (repo / "src/clamp.js").write_text("function clamp(value, min, max) {\n  return Math.min(Math.max(value, min), max);\n}\n\nmodule.exports = { clamp };\n")
    session = codex(repo)
    session.prompt("clamp() should throw a RangeError when min is above max; add a test.")
    session.write("test/clamp.test.js", JEST_TEST + VITEST_RANGE)
    wrap = (lambda body: "\n> brightline@1.0.0 test\n> jest\n\n" + body) if command == "npm test" else (lambda body: body)
    session.run(command, wrap(JEST_RED))
    session.replace("src/clamp.js", "  return Math.min(", "  if (min > max) throw new RangeError(`min ${min} is above max ${max}`);\n  return Math.min(")
    session.run(command, wrap(JEST_GREEN))
    out = session.stop(f"Done. `clamp` now throws `RangeError` for min > max. `{command}`: Tests: 3 passed, 3 total.")
    assert_silent(session, out)


NODE_TEST = """import { test } from "node:test";
import assert from "node:assert/strict";
import { clamp } from "../src/clamp.ts";

test("clamps below the min", () => {
  assert.equal(clamp(-1, 0, 10), 0);
});

test("clamps above the max", () => {
  assert.equal(clamp(12, 0, 10), 10);
});
"""
NODE_RANGE = '\ntest("rejects min above max", () => {\n  assert.throws(() => clamp(1, 5, 0), RangeError);\n});\n'
WARNING = (
    "(node:41210) ExperimentalWarning: Type Stripping is an experimental feature and might change at any time\n"
    "(Use `node --trace-warnings ...` to show where the warning was created)\n"
)
TAP_RED = (
    "TAP version 13\n" + WARNING
    + "# Subtest: clamps below the min\nok 1 - clamps below the min\n  ---\n  duration_ms: 0.52\n  ...\n"
    "# Subtest: clamps above the max\nok 2 - clamps above the max\n  ---\n  duration_ms: 0.08\n  ...\n"
    "# Subtest: rejects min above max\nnot ok 3 - rejects min above max\n  ---\n  duration_ms: 0.61\n"
    "  location: '/tmp/brightline/test/clamp.test.ts:13:1'\n  failureType: 'testCodeFailure'\n"
    "  error: 'Missing expected exception (RangeError).'\n  code: 'ERR_ASSERTION'\n  ...\n"
    "1..3\n# tests 3\n# suites 0\n# pass 2\n# fail 1\n# cancelled 0\n# skipped 0\n# todo 0\n# duration_ms 58.1\n"
)
TAP_GREEN = (
    "TAP version 13\n" + WARNING
    + "# Subtest: clamps below the min\nok 1 - clamps below the min\n  ---\n  duration_ms: 0.52\n  ...\n"
    "# Subtest: clamps above the max\nok 2 - clamps above the max\n  ---\n  duration_ms: 0.08\n  ...\n"
    "# Subtest: rejects min above max\nok 3 - rejects min above max\n  ---\n  duration_ms: 0.11\n  ...\n"
    "1..3\n# tests 3\n# suites 0\n# pass 3\n# fail 0\n# cancelled 0\n# skipped 0\n# todo 0\n# duration_ms 55.0\n"
)


def test_node_test_tap_with_stderr_warning_fail_fix_pass(tmp_path, codex):
    session = codex(brightline(tmp_path, "node", "test/clamp.test.ts", NODE_TEST, script="node --test"))
    session.prompt("clamp() should throw a RangeError when min is above max; add a test.")
    session.write("test/clamp.test.ts", NODE_TEST + NODE_RANGE)
    session.run("node --test --test-reporter=tap", TAP_RED)
    session.write("src/clamp.ts", CLAMP_FIXED)
    session.run("node --test --test-reporter=tap", TAP_GREEN)
    out = session.stop("Done. `clamp(1, 5, 0)` throws a RangeError now. `node --test --test-reporter=tap`: 3 pass, 0 fail (plus Node's type-stripping warning).")
    assert_silent(session, out)


ANSI_SPEC_GREEN = (
    WARNING
    + "\x1b[32m✔ clamps below the min \x1b[90m(0.51ms)\x1b[39m\x1b[39m\n"
    "\x1b[32m✔ clamps above the max \x1b[90m(0.07ms)\x1b[39m\x1b[39m\n"
    "\x1b[32m✔ rejects min above max \x1b[90m(0.12ms)\x1b[39m\x1b[39m\n"
    "\x1b[34mℹ tests 3\x1b[39m\n\x1b[34mℹ suites 0\x1b[39m\n\x1b[34mℹ pass 3\x1b[39m\n\x1b[34mℹ fail 0\x1b[39m\n"
    "\x1b[34mℹ cancelled 0\x1b[39m\n\x1b[34mℹ skipped 0\x1b[39m\n\x1b[34mℹ todo 0\x1b[39m\n\x1b[34mℹ duration_ms 60.12\x1b[39m\n"
)
ANSI_SPEC_RED = (
    WARNING
    + "\x1b[32m✔ clamps below the min \x1b[90m(0.51ms)\x1b[39m\x1b[39m\n"
    "\x1b[32m✔ clamps above the max \x1b[90m(0.07ms)\x1b[39m\x1b[39m\n"
    "\x1b[31m✖ rejects min above max \x1b[90m(0.66ms)\x1b[39m\x1b[39m\n"
    "\x1b[34mℹ tests 3\x1b[39m\n\x1b[34mℹ suites 0\x1b[39m\n\x1b[34mℹ pass 2\x1b[39m\n\x1b[34mℹ fail 1\x1b[39m\n"
    "\x1b[34mℹ cancelled 0\x1b[39m\n\x1b[34mℹ skipped 0\x1b[39m\n\x1b[34mℹ todo 0\x1b[39m\n\x1b[34mℹ duration_ms 61.40\x1b[39m\n\n"
    "\x1b[31m✖ failing tests:\x1b[39m\n\ntest at test/clamp.test.ts:13:1\n"
    "\x1b[31m✖ rejects min above max \x1b[90m(0.66ms)\x1b[39m\x1b[39m\n"
    "  AssertionError [ERR_ASSERTION]: Missing expected exception (RangeError).\n"
)


@pytest.mark.parametrize("script", ["tsc --noEmit && node --test", "node --test"])
def test_npm_test_ansi_spec_reporter_with_tsc_fail_fix_pass(tmp_path, codex, script):
    session = codex(brightline(tmp_path, "node", "test/clamp.test.ts", NODE_TEST, script=script))
    session.prompt("clamp() should throw a RangeError when min is above max; add a test.")
    session.write("test/clamp.test.ts", NODE_TEST + NODE_RANGE)
    session.run("npm test", f"\n> brightline@1.0.0 test\n> {script}\n\n" + ANSI_SPEC_RED + "npm error Lifecycle script `test` failed with error:\nnpm error code 1\n")
    session.write("src/clamp.ts", CLAMP_FIXED)
    session.run("npm test", f"\n> brightline@1.0.0 test\n> {script}\n\n" + ANSI_SPEC_GREEN)
    out = session.stop("Done. `clamp` throws a RangeError when min > max, and there is a test for it. `npm test` (tsc, then node --test): 3 pass, 0 fail.")
    assert_silent(session, out)


def test_npm_test_tsc_error_then_green(tmp_path, codex):
    """tsc fails first (a type error in the new test), so node --test never ran; fixed, green."""
    session = codex(brightline(tmp_path, "node", "test/clamp.test.ts", NODE_TEST, script="tsc --noEmit && node --test"))
    session.prompt("clamp() should throw a RangeError when min is above max; add a test.")
    session.write("test/clamp.test.ts", NODE_TEST + NODE_RANGE.replace("clamp(1, 5, 0)", "clamp(1, 5)"))
    session.write("src/clamp.ts", CLAMP_FIXED)
    session.run(
        "npm test",
        "\n> brightline@1.0.0 test\n> tsc --noEmit && node --test\n\n"
        "test/clamp.test.ts(14,23): error TS2554: Expected 3 arguments, but got 2.\n"
        "npm error Lifecycle script `test` failed with error:\nnpm error code 2\n",
    )
    session.replace("test/clamp.test.ts", "clamp(1, 5)", "clamp(1, 5, 0)")
    session.run("npm test", "\n> brightline@1.0.0 test\n> tsc --noEmit && node --test\n\n" + ANSI_SPEC_GREEN)
    out = session.stop("Done. My first test call had a type error (missing argument); fixed. `npm test`: tsc clean, 3 pass, 0 fail.")
    assert_silent(session, out)
