"""G3b: strict "last summary wins" parsers, checked against real runner output.

`tests/fixtures/runner_outputs/` holds D2's labelled corpus from Stage 1: 49 outputs
captured live from real runners (`real.json`) and 55 reconstructed from each tool's
documented default reporter (`reconstructed.json`; wrapper rows reuse a live capture).
`expected` is what the run actually did: True passed, False failed, None ran no tests or
is not a run.

The previous parser gave 8 confident wrong verdicts on these 104 cases (5 wrong PASS:
jest "Test suite failed to run" twice, a cargo failure in the second binary, `go test
| tail -2`, `go test -run NoMatch`; 3 wrong FAIL: an app log under `pytest -s`, a vitest
test named "...JobStatus.FAILED", deno's "0 failed"). The rule pinned here is the one
that matters: a verdict may be missing, but it is never wrong.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from truthstone.verify import parsers, runners

CORPUS_DIR = Path(__file__).parent / "fixtures" / "runner_outputs"
CORPUS = [
    *json.loads((CORPUS_DIR / "real.json").read_text()),
    *json.loads((CORPUS_DIR / "reconstructed.json").read_text()),
]


def _text(case: dict) -> str:
    return runners.output_text({"stdout": case["stdout"], "stderr": case["stderr"]})


class TestRealisticRunnerOutputs:
    def test_the_corpus_is_the_stage_one_corpus(self):
        assert len(CORPUS) == 104
        assert sum(1 for case in CORPUS if case["source"] == "real") == 49

    @pytest.mark.parametrize("case", CORPUS, ids=[case["id"] for case in CORPUS])
    def test_a_verdict_is_never_wrong(self, case):
        outcome = runners.parse_output(case["command"], _text(case))
        assert outcome.passed is None or outcome.passed == case["expected"], (
            f"{case['id']}: parsed {outcome.passed} ({outcome.summary!r}), actually {case['expected']}"
        )

    def test_most_runs_get_a_verdict(self):
        """Silence is safe but useless. 93 of 104 today; the misses are `pytest -qq`
        (no summary printed), a summary cut off by `| head -3`, runs that ran nothing,
        and Bazel, which is not parsed."""
        correct = sum(
            runners.parse_output(case["command"], _text(case)).passed == case["expected"]
            and case["expected"] is not None
            for case in CORPUS
        )
        assert correct >= 85, correct


class TestTheRules:
    def test_ansi_colour_is_stripped(self):
        text = "\x1b[1m\x1b[31mTests:       \x1b[39m\x1b[22m1 failed, \x1b[32m4 passed\x1b[39m, 5 total\n"
        assert runners.parse_output("npx jest", text).passed is False

    def test_the_last_summary_wins(self):
        """An earlier summary is test output (a test that prints one, or a previous run)."""
        text = "== 3 failed in 0.1s ==\n...\n== 5 passed in 0.2s ==\n"
        outcome = runners.parse_output("pytest", text)
        assert outcome.passed is True
        assert outcome.total == 5

    def test_an_unknown_word_voids_the_summary(self):
        assert parsers.parse_pytest("== 3 passed, 2 exploded in 0.1s ==\n") is None

    def test_a_summary_must_agree_with_its_counts(self):
        assert parsers.parse_cargo("test result: ok. 1 passed; 2 failed; 0 ignored; 0 measured\n") is None

    def test_no_tests_is_its_own_outcome(self):
        for command, text in [
            ("pytest", "no tests ran in 0.01s\n"),
            ("pytest", "===== 3 skipped in 0.4s =====\n"),
            ("go test -run Nope ./...", "ok  \tex.com/calc\t(cached) [no tests to run]\n"),
            ("go test ./...", "?   \tex.com/x\t[no test files]\n"),
            ("cargo test", "test result: ok. 0 passed; 0 failed; 4 ignored; 0 measured; 0 filtered out\n"),
            ("python -m unittest", "-" * 70 + "\nRan 0 tests in 0.000s\n\nNO TESTS RAN\n"),
        ]:
            outcome = runners.parse_output(command, text)
            assert outcome.passed is None, (command, text)
            assert outcome.summary.startswith("no tests ran"), outcome.summary

    def test_the_bare_failed_count_fallback_is_gone(self):
        """`\\b\\d+ failed\\b` anywhere in an unknown runner's output was a failing run."""
        assert runners.parse_output("make check", "import done: 3 failed rows skipped\n").passed is None
        assert runners.parse_output("npm test", "Traceback (most recent call last):\n  ...\n").passed is None

    def test_disagreeing_summaries_under_a_wrapper_give_no_verdict(self):
        text = "== 4 passed in 0.1s ==\nTests:       1 failed, 2 passed, 3 total\n"
        assert runners.parse_output("make test", text).passed is None

    def test_a_wrapper_reads_the_tool_underneath(self):
        jest = "Test Suites: 1 passed, 1 total\nTests:       5 passed, 5 total\n"
        assert runners.parse_output("npm test", "\n> app@1.0.0 test\n> jest\n\n" + jest).passed is True
        assert runners.parse_output("make test", "pytest -q\n1 failed, 2 passed in 0.01s\n").passed is False


RULE = "-" * 70 + "\n"
NODE_TAP_FAIL = (
    "# tests 2\n# suites 0\n# pass 1\n# fail 1\n# cancelled 0\n# skipped 0\n# todo 0\n# duration_ms 41.2\n"
)
BUN_PASS = " 2 pass\n 1 skip\n 0 fail\n 2 expect() calls\nRan 3 tests across 1 file. [164.00ms]\n"
VITEST_FAIL = " Test Files  1 failed | 1 passed (2)\n      Tests  1 failed | 4 passed (5)\n"
PLAYWRIGHT_FAIL = "Running 6 tests using 3 workers\n\n  1 failed\n    x\n  5 passed (6.1s)\n"
CARGO_SECOND_BINARY_FAILS = (
    "test result: ok. 2 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out\n"
    "test result: FAILED. 0 passed; 1 failed; 0 ignored; 0 measured; 0 filtered out\n"
)
NEXTEST = "     Summary [   0.010s] 5 tests run: "
DOTNET = "!  - Failed:     {}, Passed:     {}, Skipped:     0, Total:     3, Duration: 4 ms\n"
MAVEN = "[{}] Tests run: 3, Failures: {}, Errors: 0, Skipped: 0\n[INFO] BUILD {}\n"
XCTEST = "\tExecuted 4 tests, with {} (0 unexpected) in 0.010 (0.012) seconds\n"


class TestFormats:
    @pytest.mark.parametrize(
        ("command", "text", "passed"),
        [
            # pytest: -q (no rule), xdist, timing suffix, collection error, a noisy log
            ("pytest -q", "F.\n1 failed, 1 passed in 0.02s\n", False),
            ("pytest -n auto", "== 1 failed, 119 passed in 3.40s ==\n", False),
            ("pytest", "== 12 passed, 3 warnings in 61.20s (0:01:01) ==\n", True),
            ("pytest", "!!! Interrupted: 1 error during collection !!!\n== 1 error in 0.12s ==\n", False),
            ("pytest -s", "log: 2 errors, 3 failed rows\n.\n== 1 passed in 0.00s ==\n", True),
            # unittest and Django
            ("python -m unittest", RULE + "Ran 3 tests in 0.001s\n\nOK\n", True),
            ("python -m unittest", RULE + "Ran 3 tests in 0.001s\n\nOK (skipped=1)\n", True),
            ("python -m unittest", RULE + "Ran 3 tests in 0.001s\n\nFAILED (failures=1, errors=1)\n", False),
            ("python manage.py test", RULE + "Ran 5 tests in 0.012s\n\nOK\nDestroying test db...\n", True),
            # jest, vitest (no colon), mocha, node:test, bun, deno, playwright
            ("npx jest", "Test Suites: 1 failed, 1 passed, 2 total\nTests:       4 passed, 4 total\n", False),
            ("npx vitest run", " Test Files  1 passed (1)\n      Tests  4 passed (4)\n", True),
            ("npx vitest run", VITEST_FAIL, False),
            ("npx vitest run", " Test Files  1 failed (1)\n      Tests  no tests\n", False),
            ("npx mocha", "  2 passing (6ms)\n  1 pending\n", True),
            ("npx mocha", "  1 passing (7ms)\n  1 failing\n", False),
            ("node --test", NODE_TAP_FAIL, False),
            ("bun test", BUN_PASS, True),
            ("bun test", " 1 pass\n 1 fail\nRan 2 tests across 1 file. [12.00ms]\n", False),
            ("deno test", "ok | 2 passed | 0 failed (12ms)\n", True),
            ("deno test", "FAILED | 1 passed | 1 failed (14ms)\n", False),
            ("npx playwright test", PLAYWRIGHT_FAIL, False),
            # go, cargo, nextest
            ("go test ./...", "ok  \tex.com/calc\t0.01s\n?   \tex.com/x\t[no test files]\n", True),
            ("go test ./...", "--- FAIL: TestAdd (0.00s)\nFAIL\nFAIL\tex.com/calc\t0.1s\nFAIL\n", False),
            ("go test ./... | tail -2", "ok  \tex.com/ok\t(cached)\nFAIL\n", False),
            ("go test ./...", "FAIL\tex.com/calc [build failed]\n", False),
            ("cargo test", CARGO_SECOND_BINARY_FAILS, False),
            ("cargo nextest run", NEXTEST + "5 passed, 0 skipped\n", True),
            ("cargo nextest run", NEXTEST + "4 passed (1 slow), 1 failed, 0 skipped\n", False),
            # Ruby, PHP, .NET, JVM, Swift, Elixir
            ("bundle exec rspec", "Finished in 0.01 seconds\n3 examples, 0 failures\n", True),
            ("bundle exec rspec", "3 examples, 1 failure\n", False),
            ("bundle exec rspec", "0 examples, 0 failures, 1 error occurred outside of examples\n", False),
            ("ruby -Itest test/x_test.rb", "2 runs, 1 assertions, 0 failures, 0 errors, 1 skips\n", True),
            ("vendor/bin/phpunit", "OK (3 tests, 3 assertions)\n", True),
            ("vendor/bin/phpunit", "FAILURES!\nTests: 3, Assertions: 3, Failures: 1.\n", False),
            ("dotnet test", "Passed" + DOTNET.format(0, 3), True),
            ("dotnet test", "Failed" + DOTNET.format(1, 2), False),
            ("./gradlew test", "> Task :compileJava\n> Task :test\n\nBUILD SUCCESSFUL in 3s\n", True),
            ("./gradlew test", "3 tests completed, 1 failed\n\nBUILD FAILED in 2s\n", False),
            ("mvn test", MAVEN.format("INFO", 0, "SUCCESS"), True),
            ("mvn test", MAVEN.format("ERROR", 1, "FAILURE"), False),
            ("swift test", XCTEST.format("0 failures"), True),
            ("swift test", XCTEST.format("1 failure"), False),
            ("mix test", "Finished in 0.03 seconds\n1 doctest, 3 tests, 0 failures\n", True),
            ("mix test", "Finished in 0.03 seconds\n3 tests, 1 failure\n", False),
        ],
    )
    def test_each_format(self, command, text, passed):
        assert runners.parse_output(command, text).passed is passed

    def test_cargo_counts_every_binary(self):
        text = (
            "test result: ok. 2 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s\n"
            "test result: ok. 3 passed; 0 failed; 1 ignored; 0 measured; 0 filtered out; finished in 0.00s\n"
        )
        outcome = runners.parse_output("cargo test", text)
        assert outcome.passed is True
        assert outcome.total == 6

    def test_go_json_events_are_read(self):
        text = (
            '{"Action":"run","Package":"ex.com/calc","Test":"TestAdd"}\n'
            '{"Action":"pass","Package":"ex.com/calc","Test":"TestAdd","Elapsed":0}\n'
            '{"Action":"pass","Package":"ex.com/calc","Elapsed":0.002}\n'
        )
        assert runners.parse_output("go test -json ./calc", text).passed is True

    def test_failure_counts_include_errors(self):
        outcome = runners.parse_output("pytest", "== 2 failed, 1 error, 7 passed in 1.0s ==\n")
        assert (outcome.passed, outcome.failed, outcome.total) == (False, 3, 10)

    def test_huge_output_is_bounded(self):
        text = "x" * 2_000_000 + "\n== 3 passed in 0.1s ==\n"
        assert runners.parse_output("pytest", text).passed is True
