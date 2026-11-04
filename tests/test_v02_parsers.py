"""node:test's TAP reporter names a failing test's file in its YAML diagnostics (`location:`).

Class: `node --test` (and `npm test` running it) prints TAP when stdout is not a terminal,
which is how agents run it. The failing file is what links a failure to the change (v0.2
(b)); passing subtests carry no location, so only failures are named.
"""

from __future__ import annotations

from truthstone.verify import parsers

TAP = """TAP version 13
# Subtest: adds
ok 1 - adds
  ---
  duration_ms: 0.4
  type: 'test'
  ...
# Subtest: rounds up
not ok 2 - rounds up
  ---
  duration_ms: 0.6
  type: 'test'
  location: '/work/repo/test/rounding.test.ts:12:1'
  failureType: 'testCodeFailure'
  error: 'Expected values to be strictly equal'
  ...
1..2
# tests 2
# pass 1
# fail 1
"""


def test_a_tap_failure_names_its_file():
    assert parsers.failing_files(TAP) == ("/work/repo/test/rounding.test.ts",)


def test_a_passing_tap_run_names_nothing():
    passing = TAP.replace("not ok 2", "ok 2").replace(
        "  location: '/work/repo/test/rounding.test.ts:12:1'\n", ""
    )
    assert parsers.failing_files(passing) == ()
