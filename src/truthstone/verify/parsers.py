"""Strict test-summary parsers: the last summary wins (G3b).

The Completion Gate reads the agent's own test output, so a parser that guesses turns
into an accusation. The previous parser summed counts found anywhere in the text, read
only the first cargo summary, and trusted a bare ``"FAIL" in text``. On 104 labelled
runner outputs (49 captured live, docs/IMPROVEMENTS.md G3b) it gave **7 confident wrong
verdicts**: a jest "Test suite failed to run" read as a pass, a cargo failure in the
second test binary missed, ``go test -run NoMatch`` read as a pass — and, the other way,
an application log line "2 errors, 3 failed rows" under ``pytest -s`` read as a failing
run.

These parsers follow Pebble's rules, and the core of them is a port:

* **ANSI codes and carriage returns are stripped** before anything is matched;
* **each parser anchors on its framework's own summary line**, matched in full, and
  **the last one wins** — a summary is printed at the end, so anything earlier is test
  output, which a test controls;
* **words are whitelisted**: an unknown word in a summary voids it rather than being
  guessed at;
* **counts must agree with the verdict word** (cargo's ``ok`` with failures is not a
  summary cargo prints, so it is not one);
* **"no tests ran" is its own outcome**, never a failure and never a pass;
* summaries that are per binary or per package (cargo, go, dotnet, maven) are summed, so
  one failing binary fails the run.

Provenance: ported from Pebble ``backend/pebble/recipes.py`` (lines 870-1049, the strict
summary parsers; same owner, Apache-2.0) and extended to bun, deno, nextest, rspec,
minitest, PHPUnit, dotnet, Gradle, Maven, Playwright, Swift and ExUnit. Pebble's go parser
called a plain ``ok`` package "no tests"; here an ``ok`` package without
``[no tests to run]`` is a pass, and ``go test -json`` is read too.

A test process still controls its own output. These parsers raise the bar for a stray
line to be mistaken for a summary; they cannot make output trustworthy, which is why the
exit status leads wherever it is the runner's (``runners.outcome_from_result``).
"""

from __future__ import annotations

import json
import re
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

__all__ = ["PARSERS", "RUNNER_PARSERS", "Summary", "clean", "parse"]

# Output beyond this is not read: summaries are at the end (hosts already truncate long
# tool output; Claude Code keeps the first and last 5,000 characters of a failure). The
# head is kept too, for runners that print one summary per binary or package.
MAX_TEXT = 256_000
_HEAD = 64_000


@dataclass(frozen=True, slots=True)
class Summary:
    """What one framework summary says. ``status`` is passed | failed | no_tests."""

    end: int
    status: str
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: int = 0
    total: int = 0
    line: str = ""


def _counted(end: int, line: str, passed: int, failed: int, skipped: int, errors: int, total: int) -> Summary:
    """Pebble's ``classify``: a failure or error fails it; no passing test is "no tests"."""
    if failed or errors:
        status = "failed"
    elif total == 0 or not passed:
        status = "no_tests"
    else:
        status = "passed"
    return Summary(end, status, passed, failed, skipped, errors, total, _tidy(line))


def _tidy(line: str) -> str:
    return line.strip().strip("=").strip()[:200]


ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def clean(text: str) -> str:
    text = text if isinstance(text, str) else ""
    if len(text) > MAX_TEXT:
        text = text[:_HEAD] + "\n" + text[-(MAX_TEXT - _HEAD) :]
    return ANSI.sub("", text.replace("\r\n", "\n").replace("\r", "\n"))


def _last(pattern: re.Pattern[str], text: str) -> re.Match[str] | None:
    last = deque(pattern.finditer(text), maxlen=1)
    return last[0] if last else None


def _items(text: str, separator: str) -> dict[str, int] | None:
    """``"1 failed, 4 passed"`` -> counts; a repeated or malformed item voids it."""
    counts: dict[str, int] = {}
    for item in filter(None, (part.strip() for part in text.split(separator))):
        number, _, word = item.partition(" ")
        if not number.isdigit() or not word or word in counts:
            return None
        counts[word] = int(number)
    return counts


# -- Python ------------------------------------------------------------------------------

UNITTEST = re.compile(
    r"^-{70}\nRan (\d+) tests? in \d+\.\d+s\n\n(OK|FAILED|NO TESTS RAN)(?: \(([^()\n]*)\))?[ \t]*$", re.M
)
UNITTEST_ITEM = re.compile(r"(failures|errors|skipped|expected failures|unexpected successes)=(\d+)")
PYTEST_LINE = re.compile(r"^(?:=+ )?(?:no tests ran|\d+ [a-z]).* in \d+(?:\.\d+)?s\b.*$", re.M)
PYTEST_STRICT = re.compile(
    r"(?:=+ )?(no tests ran|\d+ [a-z]+(?: [a-z]+)?(?:, \d+ [a-z]+(?: [a-z]+)?)*) in \d+(?:\.\d+)?s"
    r"(?: \(\d+:\d{2}:\d{2}\))?(?: =+)?"
)
PYTEST_WORDS = {
    "passed": "passed", "xpassed": "passed", "failed": "failed", "error": "errors", "errors": "errors",
    "skipped": "skipped", "xfailed": "skipped", "deselected": None, "warning": None, "warnings": None,
    "rerun": None, "subtests passed": None, "subtests skipped": None, "subtests xfailed": None,
    "subtests xpassed": None, "subtests failed": "failed",
}


def parse_unittest(text: str) -> Summary | None:
    match = _last(UNITTEST, text)
    if not match:
        return None
    total, status = int(match[1]), match[2]
    counts: dict[str, int | None] = dict.fromkeys(
        ("failures", "errors", "skipped", "expected failures", "unexpected successes")
    )
    for item in match[3].split(", ") if match[3] is not None else ():
        part = UNITTEST_ITEM.fullmatch(item)
        if not part or counts[part[1]] is not None:
            return None
        counts[part[1]] = int(part[2])
    n = {key: value or 0 for key, value in counts.items()}
    failed = n["failures"] + n["unexpected successes"]
    errors, skipped = n["errors"], n["skipped"] + n["expected failures"]
    consistent = {
        "OK": not (failed or errors),
        "FAILED": bool(failed or errors),
        "NO TESTS RAN": not (total or failed or errors),
    }[status]
    if not consistent:
        return None
    line = f"Ran {total} tests: {status}" + (f" ({match[3]})" if match[3] else "")
    passed = max(0, total - failed - errors - skipped)
    return _counted(match.end(), line, passed, failed, skipped, errors, total)


def parse_pytest(text: str) -> Summary | None:
    match = _last(PYTEST_LINE, text)
    strict = PYTEST_STRICT.fullmatch(match[0]) if match else None
    if not strict:
        return None
    counts = dict.fromkeys(("passed", "failed", "skipped", "errors"), 0)
    if strict[1] != "no tests ran":
        seen: set[str] = set()
        for item in strict[1].split(", "):
            number, word = item.split(" ", 1)
            if word not in PYTEST_WORDS or word in seen:
                return None
            seen.add(word)
            bucket = PYTEST_WORDS[word]
            if bucket:
                counts[bucket] += int(number)
    total = sum(counts.values())
    return _counted(
        match.end(), match[0], counts["passed"], counts["failed"], counts["skipped"], counts["errors"], total
    )


# -- JavaScript --------------------------------------------------------------------------

_INFO_SIGN = chr(0x2139)  # the spec reporter's line marker ("information source")
NODE = re.compile(  # node:test's TAP (`#`) and spec reporters
    r"^([#" + _INFO_SIGN + r"]) tests (\d+)\n\1 suites (\d+)\n\1 pass (\d+)\n\1 fail (\d+)\n"
    r"\1 cancelled (\d+)\n"
    r"\1 skipped (\d+)\n\1 todo (\d+)\n\1 duration_ms \d+(?:\.\d+)?$",
    re.M,
)
JEST = re.compile(r"^Tests:\s+((?:\d+ (?:failed|skipped|todo|passed), )*)(\d+) total$", re.M)
JEST_SUITES = re.compile(r"^Test Suites:\s+((?:\d+ (?:failed|skipped|passed), )*)(\d+) total$", re.M)
MOCHA = re.compile(
    r"^ {2}(\d+) passing \(\d+(?:ms|s|m)\)$(?:\n {2}(\d+) pending$)?(?:\n {2}(\d+) failing$)?", re.M
)
_VITEST_WORDS = r"(?:failed|passed|skipped|todo)"
VITEST = re.compile(
    rf"^ *Tests  (\d+ {_VITEST_WORDS}(?: \| \d+ {_VITEST_WORDS})*) \((\d+)\)$|^ *Tests  no tests$", re.M
)
VITEST_FILES = re.compile(
    rf"^ *Test Files  (\d+ {_VITEST_WORDS}(?: \| \d+ {_VITEST_WORDS})*) \((\d+)\)$"
    r"|^ *Test Files  no tests$",
    re.M,
)
VITEST_ERRORS = re.compile(r"^ *Errors  (\d+) errors?$", re.M)
BUN_RAN = re.compile(r"^Ran (\d+) tests? across (\d+) files?\. \[\d+(?:\.\d+)?m?s\]$", re.M)
BUN_COUNT = re.compile(r"^ ?(\d+) (pass|skip|todo|fail|errors?|snapshots?|expect\(\) calls?)$")
DENO = re.compile(r"^(ok|FAILED) \| (.+) \(\d+(?:\.\d+)?m?s\)$", re.M)
DENO_ITEM = re.compile(r"(\d+) (passed|failed|ignored|filtered out|measured)(?: \(\d+ steps?\))?")
PLAYWRIGHT_RUNNING = re.compile(r"^Running (\d+) tests? using \d+ workers?", re.M)
PLAYWRIGHT_COUNT = re.compile(
    r"^ {2}(\d+) (passed|failed|flaky|skipped|did not run|interrupted)(?: \(\d+(?:\.\d+)?m?s\))?$", re.M
)


def parse_node(text: str) -> Summary | None:
    match = _last(NODE, text)
    if not match:
        return None
    total, _, passed, failed, cancelled, skipped, todo = map(int, match.groups()[1:])
    line = f"tests {total}, pass {passed}, fail {failed}" + (f", cancelled {cancelled}" if cancelled else "")
    return _counted(match.end(), line, passed, failed, skipped + todo, cancelled, total)


def parse_jest(text: str) -> Summary | None:
    match = _last(JEST, text)
    counts = _items(match[1], ",") if match else None
    if counts is None:
        return None
    suites = _last(JEST_SUITES, text)
    suite_counts = (_items(suites[1], ",") if suites else None) or {}
    # A suite that failed to run (an import error) contributes no failed *test*, so jest's
    # "Tests:" line can read all-green. The suites line is the evidence.
    errors = suite_counts.get("failed", 0) if not counts.get("failed") else 0
    line = match[0] if not errors else f"{match[0]}; {suites[0]}"
    return _counted(
        match.end(), line, counts.get("passed", 0), counts.get("failed", 0),
        counts.get("skipped", 0) + counts.get("todo", 0), errors, int(match[2]),
    )


def parse_mocha(text: str) -> Summary | None:
    match = _last(MOCHA, text)
    if not match:
        return None
    passed, pending, failed = int(match[1]), int(match[2] or 0), int(match[3] or 0)
    line = " ".join(match[0].split())
    return _counted(match.end(), line, passed, failed, pending, 0, passed + pending + failed)


def parse_vitest(text: str) -> Summary | None:
    tests = _last(VITEST, text)
    files = _last(VITEST_FILES, text)
    if not tests and not files:
        return None
    counts = _items(tests[1], "|") if tests and tests[1] else {}
    file_counts = _items(files[1], "|") if files and files[1] else {}
    if counts is None or file_counts is None:
        return None
    errors_line = _last(VITEST_ERRORS, text)
    # A file that failed to load has no failed test; vitest says so on "Test Files".
    errors = file_counts.get("failed", 0) if not counts.get("failed") else 0
    errors += int(errors_line[1]) if errors_line else 0
    total = int(tests[2]) if tests and tests[2] else 0
    end = max(m.end() for m in (tests, files, errors_line) if m)
    line = "; ".join(" ".join(m[0].split()) for m in (files, tests) if m)
    return _counted(
        end, line, counts.get("passed", 0), counts.get("failed", 0),
        counts.get("skipped", 0) + counts.get("todo", 0), errors, total,
    )


def parse_bun(text: str) -> Summary | None:
    match = _last(BUN_RAN, text)
    if not match:
        return None
    counts: dict[str, int] = {}
    lines = text[: match.start()].rstrip("\n").split("\n")
    for raw in reversed(lines[-8:]):
        item = BUN_COUNT.match(raw)
        if not item:
            break
        word = item[2].rstrip("s") if item[2] in ("errors", "snapshots") else item[2]
        counts[word] = int(item[1])
    total = int(match[1])
    passed, failed = counts.get("pass", 0), counts.get("fail", 0)
    if passed + failed > total:
        return None
    line = f"{passed} pass, {failed} fail; ran {total} tests across {match[2]} files"
    skipped = counts.get("skip", 0) + counts.get("todo", 0)
    return _counted(match.end(), line, passed, failed, skipped, counts.get("error", 0), total)


def parse_deno(text: str) -> Summary | None:
    match = _last(DENO, text)
    if not match:
        return None
    counts: dict[str, int] = {}
    for item in match[2].split(" | "):
        part = DENO_ITEM.fullmatch(item.strip())
        if not part or part[2] in counts:
            return None
        counts[part[2]] = int(part[1])
    if "passed" not in counts or "failed" not in counts or (match[1] == "ok") != (counts["failed"] == 0):
        return None
    passed, failed, ignored = counts["passed"], counts["failed"], counts.get("ignored", 0)
    return _counted(match.end(), match[0], passed, failed, ignored, 0, passed + failed + ignored)


def parse_playwright(text: str) -> Summary | None:
    running = _last(PLAYWRIGHT_RUNNING, text)
    if not running:
        return None
    counts: dict[str, int] = {}
    end = running.end()
    for item in PLAYWRIGHT_COUNT.finditer(text, running.end()):
        counts[item[2]] = int(item[1])
        end = item.end()
    if not counts:
        return None
    passed = counts.get("passed", 0) + counts.get("flaky", 0)
    failed = counts.get("failed", 0)
    errors = counts.get("interrupted", 0)
    skipped = counts.get("skipped", 0) + counts.get("did not run", 0)
    line = ", ".join(f"{n} {word}" for word, n in counts.items())
    return _counted(end, line, passed, failed, skipped, errors, int(running[1]))


# -- Go and Rust -------------------------------------------------------------------------

GO_TEST = re.compile(r"^--- (PASS|FAIL|SKIP): \S+ \(\d+(?:\.\d+)?s\)$", re.M)
GO_PACKAGE = re.compile(
    r"^(?:(?P<ok>ok  )\t\S+\t(?:\d+(?:\.\d+)?s|\(cached\))(?P<tail>[ \t][^\n]*)?"
    r"|(?P<fail>FAIL)\t\S+\t\d+(?:\.\d+)?s"
    r"|FAIL\t\S+ \[(?P<broken>build failed|setup failed)\]"
    r"|\?   \t\S+\t(?P<empty>\[no test files\]))$",
    re.M,
)
GO_FINAL_FAIL = re.compile(r"^FAIL$", re.M)


def parse_go(text: str) -> Summary | None:
    packages = list(GO_PACKAGE.finditer(text))
    if not packages:
        return _parse_go_json(text)
    results = [m[1] for m in GO_TEST.finditer(text)]
    passed, failed, skipped = results.count("PASS"), results.count("FAIL"), results.count("SKIP")
    broken = sum(1 for m in packages if m["broken"])
    failing = sum(1 for m in packages if m["fail"])
    ran = [m for m in packages if m["ok"] and "[no tests to run]" not in (m["tail"] or "")]
    # `go test` prints a bare FAIL last whenever any package failed: under `| tail -2`
    # it can be the only failure left in the text.
    final_fail = _last(GO_FINAL_FAIL, text)
    errors = broken + (failing if not failed else 0)
    if final_fail and not (failed or errors):
        errors = 1
    if not passed and not failed:
        passed = len(ran)  # a non-verbose `ok` package ran its tests and they passed
    end = max(packages[-1].end(), final_fail.end() if final_fail else 0)
    line = f"{len(ran)} package(s) ok, {failing + broken} failed"
    if not ran and not (failed or errors):
        line = "no tests to run" if any(m["ok"] for m in packages) else "no test files"
    return _counted(end, line, passed, failed, skipped, errors, passed + failed + skipped)


def _parse_go_json(text: str) -> Summary | None:
    """``go test -json``: one JSON event per line."""
    passed = failed = skipped = failing_packages = ok_packages = 0
    seen = False
    for raw in text.splitlines():
        if not raw.startswith("{") or '"Action"' not in raw:
            continue
        try:
            event = json.loads(raw)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        seen = True
        action, test = event.get("Action"), event.get("Test")
        if test:
            passed += action == "pass"
            failed += action == "fail"
            skipped += action == "skip"
        elif action == "fail":
            failing_packages += 1
        elif action == "pass":
            ok_packages += 1
    if not seen:
        return None
    errors = failing_packages if not failed else 0
    line = f"go test -json: {passed} passed, {failed} failed, {skipped} skipped"
    return _counted(len(text), line, passed, failed, skipped, errors, passed + failed + skipped)


CARGO = re.compile(
    r"^test result: (ok|FAILED)\. (\d+) passed; (\d+) failed;(?: (\d+) ignored;)?(?: (\d+) measured;)?"
    r"(?: (\d+) filtered out;?)?(?: finished in \d+(?:\.\d+)?s)?[ \t]*$",
    re.M,
)
NEXTEST = re.compile(r"^ *Summary \[ *\d+(?:\.\d+)?s\] +(\d+)(?:/\d+)? tests? run: (.+)$", re.M)
NEXTEST_WORDS = {"passed": "passed", "failed": "failed", "skipped": "skipped", "timed out": "failed"}


def parse_cargo(text: str) -> Summary | None:
    lines = list(CARGO.finditer(text))
    if not lines:
        return None
    passed = failed = ignored = 0
    for line in lines:
        if (line[1] == "ok") == (int(line[3]) > 0):
            return None
        passed, failed, ignored = passed + int(line[2]), failed + int(line[3]), ignored + int(line[4] or 0)
    # Every binary prints its own result line; one failing binary fails the run.
    summary = f"test result over {len(lines)} binaries: {passed} passed; {failed} failed"
    return _counted(lines[-1].end(), summary, passed, failed, ignored, 0, passed + failed + ignored)


def parse_nextest(text: str) -> Summary | None:
    match = _last(NEXTEST, text)
    if not match:
        return None
    counts = dict.fromkeys(("passed", "failed", "skipped"), 0)
    for item in re.sub(r"\s*\([^)]*\)", "", match[2]).split(", "):
        number, _, word = item.strip().partition(" ")
        if not number.isdigit() or word not in NEXTEST_WORDS:
            return None
        counts[NEXTEST_WORDS[word]] += int(number)
    total = counts["passed"] + counts["failed"] + counts["skipped"]
    return _counted(match.end(), match[0], counts["passed"], counts["failed"], counts["skipped"], 0, total)


# -- Ruby, PHP, .NET, JVM, Swift, Elixir --------------------------------------------------

RSPEC = re.compile(
    r"^(\d+) examples?, (\d+) failures?(?:, (\d+) pending)?"
    r"(?:, (\d+) errors? occurred outside of examples)?$",
    re.M,
)
MINITEST = re.compile(
    r"^(\d+) (?:runs|tests), (\d+) assertions, (\d+) failures, (\d+) errors, (\d+) skips$", re.M
)
PHPUNIT_OK = re.compile(r"^OK \((\d+) tests?, (\d+) assertions?\)$", re.M)
PHPUNIT_COUNTS = re.compile(
    r"^(?:OK, but [^\n]*|FAILURES!|ERRORS!|WARNINGS!|OK but [^\n]*)\n"
    r"Tests: (\d+), Assertions: (\d+)((?:, [A-Za-z ]+: \d+)*)\.$",
    re.M,
)
PHPUNIT_NONE = re.compile(r"^No tests executed!$", re.M)
DOTNET = re.compile(
    r"^(Passed|Failed)!\s+- Failed:\s+(\d+), Passed:\s+(\d+), Skipped:\s+(\d+), Total:\s+(\d+)\b.*$", re.M
)
DOTNET_SUMMARY = re.compile(
    r"^Test summary: total: (\d+), failed: (\d+), succeeded: (\d+), skipped: (\d+)\b.*$", re.M
)
GRADLE_TESTS = re.compile(r"^(\d+) tests? completed, (\d+) failed(?:, (\d+) skipped)?$", re.M)
GRADLE_BUILD = re.compile(r"^BUILD (SUCCESSFUL|FAILED) in \S+$", re.M)
GRADLE_TEST_TASK = re.compile(r"^> Task (?::[\w-]+)*:test\w*(?P<state> [A-Z-]+)?$", re.M)
MAVEN_RESULTS = re.compile(  # the Results line: the per-class lines carry "Time elapsed"
    r"^(?:\[(?:INFO|ERROR|WARNING)\] )?Tests run: (\d+), Failures: (\d+), Errors: (\d+), "
    r"Skipped: (\d+)$",
    re.M,
)
MAVEN_BUILD = re.compile(r"^\[(?:INFO|ERROR)\] BUILD (SUCCESS|FAILURE)$", re.M)
XCTEST = re.compile(
    r"^\s*Executed (\d+) tests?, with (\d+) failures? \((\d+) unexpected\) "
    r"in \d+(?:\.\d+)? \(\d+(?:\.\d+)?\) seconds$",
    re.M,
)
SWIFT_TESTING = re.compile(
    r"^\S* ?Test run with (\d+) tests? (?:in \d+ suites? )?(passed|failed) after \d+(?:\.\d+)? seconds"
    r"(?: with (\d+) issues?)?\.$",
    re.M,
)
EXUNIT = re.compile(
    r"^((?:\d+ (?:doctests?|propert(?:y|ies)|tests?|failures?|excluded|skipped|invalid)(?:, |(?=[ \n(]|$)))+)"
    r"(?: \((\d+) excluded\))?$",
    re.M,
)


def parse_rspec(text: str) -> Summary | None:
    match = _last(RSPEC, text)
    if not match:
        return None
    examples, failures = int(match[1]), int(match[2])
    pending, outside = int(match[3] or 0), int(match[4] or 0)
    passed = examples - failures - pending
    return _counted(match.end(), match[0], passed, failures, pending, outside, examples)


def parse_minitest(text: str) -> Summary | None:
    match = _last(MINITEST, text)
    if not match:
        return None
    runs, _, failures, errors, skips = map(int, match.groups())
    return _counted(match.end(), match[0], runs - failures - errors - skips, failures, skips, errors, runs)


def parse_phpunit(text: str) -> Summary | None:
    found = [m for m in (_last(p, text) for p in (PHPUNIT_OK, PHPUNIT_COUNTS, PHPUNIT_NONE)) if m]
    if not found:
        return None
    match = max(found, key=lambda m: m.end())
    if match.re is PHPUNIT_NONE:
        return _counted(match.end(), match[0], 0, 0, 0, 0, 0)
    tests = int(match[1])
    if match.re is PHPUNIT_OK:
        return _counted(match.end(), match[0], tests, 0, 0, 0, tests)
    extra: dict[str, int] = {}
    for item in filter(None, match[3].split(", ")):
        word, _, number = item.partition(": ")
        extra[word.strip()] = int(number)
    failed, errors = extra.get("Failures", 0), extra.get("Errors", 0)
    skipped = extra.get("Skipped", 0) + extra.get("Incomplete", 0)
    passed = max(0, tests - failed - errors - skipped)
    return _counted(match.end(), match[0].split("\n")[-1], passed, failed, skipped, errors, tests)


def parse_dotnet(text: str) -> Summary | None:
    lines = list(DOTNET.finditer(text))
    if lines:
        failed = passed = skipped = total = 0
        for line in lines:  # one line per test assembly
            if (line[1] == "Passed") == (int(line[2]) > 0):
                return None
            failed, passed = failed + int(line[2]), passed + int(line[3])
            skipped, total = skipped + int(line[4]), total + int(line[5])
        summary = f"dotnet test: {passed} passed, {failed} failed, {skipped} skipped"
        return _counted(lines[-1].end(), summary, passed, failed, skipped, 0, total)
    match = _last(DOTNET_SUMMARY, text)
    if not match:
        return None
    total, failed, passed, skipped = map(int, match.groups())
    return _counted(match.end(), match[0], passed, failed, skipped, 0, total)


def parse_gradle(text: str) -> Summary | None:
    build = _last(GRADLE_BUILD, text)
    tests = _last(GRADLE_TESTS, text)
    if not build and not tests:
        return None
    end = max(m.end() for m in (build, tests) if m)
    if tests:
        total, failed, skipped = int(tests[1]), int(tests[2]), int(tests[3] or 0)
        errors = 1 if build and build[1] == "FAILED" and not failed else 0
        return _counted(end, tests[0], total - failed - skipped, failed, skipped, errors, total)
    if build[1] == "FAILED":
        return Summary(end, "failed", errors=1, line=build[0])
    # A successful build reports no counts. It verified something only if a test task ran
    # (or was up to date: Gradle skips a task whose inputs and passing result are cached).
    tasks = [
        m
        for m in GRADLE_TEST_TASK.finditer(text)
        if (m["state"] or "").strip() not in ("NO-SOURCE", "SKIPPED")
    ]
    if not tasks:
        return Summary(end, "no_tests", line=build[0])
    return Summary(end, "passed", line=f"{tasks[-1][0][2:]}; {build[0]}")


def parse_maven(text: str) -> Summary | None:
    results = list(MAVEN_RESULTS.finditer(text))
    build = _last(MAVEN_BUILD, text)
    if not results and not build:
        return None
    run = failures = errors = skipped = 0
    for line in results:  # one Results block per module (and per plugin)
        run, failures = run + int(line[1]), failures + int(line[2])
        errors, skipped = errors + int(line[3]), skipped + int(line[4])
    end = max(m.end() for m in (*results[-1:], build) if m)
    if build and build[1] == "FAILURE" and not (failures or errors):
        errors = 1
    line = f"Tests run: {run}, Failures: {failures}, Errors: {errors}, Skipped: {skipped}"
    return _counted(end, line, run - failures - errors - skipped, failures, skipped, errors, run)


def parse_swift(text: str) -> Summary | None:
    found = [m for m in (_last(XCTEST, text), _last(SWIFT_TESTING, text)) if m]
    if not found:
        return None
    match = max(found, key=lambda m: m.end())
    if match.re is XCTEST:
        total, failures = int(match[1]), int(match[2])
        return _counted(match.end(), match[0], total - failures, failures, 0, 0, total)
    total, failed = int(match[1]), match[2] == "failed"
    issues = int(match[3] or 0)
    return _counted(match.end(), match[0], 0 if failed else total, issues or int(failed), 0, 0, total)


def parse_exunit(text: str) -> Summary | None:
    match = _last(EXUNIT, text)
    if not match:
        return None
    counts: dict[str, int] = {}
    for item in filter(None, (part.strip() for part in match[1].split(","))):
        number, _, word = item.partition(" ")
        word = {"doctest": "doctests", "test": "tests", "failure": "failures", "property": "properties"}.get(
            word, word
        )
        if word in counts:
            return None
        counts[word] = int(number)
    if "tests" not in counts or "failures" not in counts:
        return None
    total = counts["tests"] + counts.get("doctests", 0) + counts.get("properties", 0)
    failures, skipped = counts["failures"], counts.get("skipped", 0) + counts.get("excluded", 0)
    errors = counts.get("invalid", 0)
    return _counted(match.end(), match[0], total - failures - errors, failures, skipped, errors, total)


# -- choosing ---------------------------------------------------------------------------------

Parser = Callable[[str], Summary | None]

PARSERS: tuple[Parser, ...] = (
    parse_node, parse_unittest, parse_pytest, parse_jest, parse_mocha, parse_vitest, parse_go,
    parse_cargo, parse_nextest, parse_bun, parse_deno, parse_playwright, parse_rspec,
    parse_minitest, parse_phpunit, parse_dotnet, parse_gradle, parse_maven, parse_swift,
    parse_exunit,
)

# The runner's own format, tried first. Wrappers (npm, make, tox, ...) print whatever the
# tool underneath prints, so they go straight to the unambiguous search over every parser.
RUNNER_PARSERS: dict[str, tuple[Parser, ...]] = {
    "pytest": (parse_pytest,),
    "hatch": (parse_pytest,),
    "unittest": (parse_unittest, parse_pytest),
    "django": (parse_unittest,),
    "jest": (parse_jest,),
    "vitest": (parse_vitest,),
    "mocha": (parse_mocha,),
    "node": (parse_node,),
    "bun": (parse_bun,),
    "deno": (parse_deno,),
    "playwright": (parse_playwright,),
    "go": (parse_go,),
    "cargo": (parse_cargo,),
    "nextest": (parse_nextest,),
    "rspec": (parse_rspec,),
    "minitest": (parse_minitest,),
    "rails": (parse_minitest, parse_rspec),
    "phpunit": (parse_phpunit,),
    "dotnet": (parse_dotnet,),
    "gradle": (parse_gradle,),
    "maven": (parse_maven,),
    "swift": (parse_swift,),
    "mix": (parse_exunit,),
}


# A substring each parser's summary must contain. Checking it first keeps the search
# over every parser to a fraction of a millisecond on ordinary output: a plain `in` is
# far cheaper than a multiline regex scan, and most outputs mention one framework.
_ANCHORS: dict[Parser, tuple[str, ...]] = {
    parse_node: ("duration_ms",),
    parse_unittest: ("\nRan ",),
    parse_pytest: (" in ",),
    parse_jest: ("Tests:",),
    parse_mocha: (" passing (",),
    parse_vitest: ("Tests  ", "Test Files  "),
    parse_go: ("ok  \t", "FAIL", "?   \t", '"Action"'),
    parse_cargo: ("test result: ",),
    parse_nextest: ("Summary [",),
    parse_bun: (" across ",),
    parse_deno: (" | ",),
    parse_playwright: ("Running ",),
    parse_rspec: (" example",),
    parse_minitest: (" assertions, ",),
    parse_phpunit: ("Assertions: ", " assertion", "No tests executed!"),
    parse_dotnet: ("Passed!", "Failed!", "Test summary:"),
    parse_gradle: ("BUILD ", " tests completed", " test completed"),
    parse_maven: ("Tests run: ", "BUILD "),
    parse_swift: ("Executed ", "Test run with "),
    parse_exunit: (" failure",),
}


def _run(parser: Parser, text: str) -> Summary | None:
    anchors = _ANCHORS.get(parser)
    if anchors and not any(anchor in text for anchor in anchors):
        return None
    return parser(text)


def parse(runner: str, text: str) -> Summary | None:
    """The summary the output reports, or None when it does not report one clearly.

    The runner's own parser first. If it finds nothing — or the runner is a wrapper such
    as ``npm test`` or ``make test`` — every parser is tried, and a result is accepted
    only when it is unambiguous: every summary found agrees on whether the run failed.
    """
    text = clean(text)
    if not text.strip():
        return None
    for parser in RUNNER_PARSERS.get(runner, ()):
        found = _run(parser, text)
        if found is not None:
            return found
    found_all = [summary for parser in PARSERS if (summary := _run(parser, text)) is not None]
    if not found_all:
        unprefixed = _without_task_prefixes(text)
        if unprefixed is None:
            return None
        found_all = [summary for parser in PARSERS if (summary := _run(parser, unprefixed)) is not None]
        if not found_all:
            return None
    statuses = {summary.status for summary in found_all}
    if "failed" in statuses and "passed" in statuses:
        return None  # two summaries disagree: no verdict rather than a guess
    preferred = "failed" if "failed" in statuses else ("passed" if "passed" in statuses else "no_tests")
    return max((s for s in found_all if s.status == preferred), key=lambda s: s.end)


# -- which test files failed (G4a: a TDD red phase fails only in the tests it wrote) -----

_FAILING_FILE = re.compile(
    r"^(?:FAILED|ERROR) (?P<py>[^\s:]+\.py)(?:::\S*)?(?:\s+-\s.*)?$"  # pytest short summary
    r"|^(?P<pyv>[^\s:]+\.py)::\S+ (?:FAILED|ERROR)\b"  # pytest -v
    r"|^\s*FAIL\s+(?P<js>\S+\.[cm]?[jt]sx?)\b"  # jest "FAIL path", vitest " FAIL  path > test"
    r"|^rspec \.?/?(?P<rb>\S+?\.rb)(?::\d+)?\b"  # rspec "rspec ./spec/x_spec.rb:4 # ..."
    r"|^test at (?P<node>\S+?\.[cm]?[jt]sx?):\d+:\d+$"  # node:test, spec reporter
    r"|^\s*location:\s*'(?P<nodetap>[^']+?\.[cm]?[jt]sx?):\d+:\d+'\s*$",  # node:test, TAP diagnostics
    re.M,
)


def failing_files(text: str) -> tuple[str, ...]:
    """Test files the output names as failing, in order. Empty when it names none (go and
    cargo name tests, not files)."""
    found: dict[str, None] = {}
    for match in _FAILING_FILE.finditer(clean(text)):
        path = next(group for group in match.groups() if group)
        while path.startswith("./"):
            path = path[2:]
        found[path] = None
    return tuple(found)


# -- which tests failed (G2b: a failing test id clears only when a later run covers it) --

_FAILING_TEST = re.compile(
    r"^(?:FAILED|ERROR) (?P<py>[^\s:]+\.py(?:::\S+)?)(?:\s+-\s.*)?$"  # pytest short summary
    r"|^(?P<pyv>[^\s:]+\.py::\S+) (?:FAILED|ERROR)\b",  # pytest -v
    re.M,
)
MAX_FAILING_TESTS = 50


def failing_tests(text: str) -> tuple[str, ...]:
    """The failing tests the output names, as pytest node ids (``path::name[param]``), in
    order. A collection error names its file. Empty when the output names none.

    Only lines that name a test with its file are read: pytest's default ``-rfE`` short summary
    lists every failure and error, so the list can be checked against the summary's counts; and
    node:test's (day 3), as ``path::title`` (``_node_failing_tests``).
    """
    found: dict[str, None] = {}
    cleaned = clean(text)
    for match in _FAILING_TEST.finditer(cleaned):
        node = match.group("py") or match.group("pyv")
        while node.startswith("./"):
            node = node[2:]
        found[node] = None
        if len(found) >= MAX_FAILING_TESTS:
            break
    for node in _node_failing_tests(cleaned):
        if len(found) >= MAX_FAILING_TESTS:
            break
        found[node] = None
    return tuple(found)


# node:test names a failing test by its title and its place. The spec reporter's closing list
# pairs `test at <path>:<line>:<col>` with the `✖ <title> (<ms>)` under it; TAP gives each
# `not ok N - <title>` a `location: '<path>:<line>:<col>'` among its diagnostics. Each pair is an
# id `path::title`, as pytest's are `path::name`.
_NODE_AT = re.compile(r"^\s*test at (?:file://)?(?P<path>\S+?\.[cm]?[jt]sx?):\d+:\d+\s*$")
_NODE_FAILED = re.compile(r"^\s*\u2716\s+(?P<title>.+?)(?:\s+\(\d+(?:\.\d+)?m?s\))?\s*$")
_TAP_NOT_OK = re.compile(r"^\s*not ok \d+ - (?P<title>.+?)(?:\s+#\s.*)?\s*$")
_TAP_RESULT = re.compile(r"^\s*(?:not )?ok \d+ ")
_TAP_LOCATION = re.compile(r"^\s*location:\s*'(?:file://)?(?P<path>[^']+?\.[cm]?[jt]sx?):\d+:\d+'\s*$")


def _node_failing_tests(text: str) -> list[str]:
    lines = text.split("\n")
    found: list[str] = []
    for n, line in enumerate(lines):
        at = _NODE_AT.match(line)
        if at:
            title = next((later for later in lines[n + 1 : n + 3] if later.strip()), "")
            failed = _NODE_FAILED.match(title)
            if failed:
                found.append(f"{_without_dot(at.group('path'))}::{failed.group('title')}")
            continue
        tap = _TAP_NOT_OK.match(line)
        if tap:
            for later in lines[n + 1 : n + 60]:
                if _TAP_RESULT.match(later):
                    break
                location = _TAP_LOCATION.match(later)
                if location:
                    found.append(f"{_without_dot(location.group('path'))}::{tap.group('title')}")
                    break
    return found


def _without_dot(path: str) -> str:
    while path.startswith("./"):
        path = path[2:]
    return path


# `turbo run test` and similar monorepo runners prefix every line with `<package>:<task>: `.
_TASK_PREFIX = re.compile(r"^[\w@./-]+:[\w:.-]+: ?", re.M)


def _without_task_prefixes(text: str) -> str | None:
    """The text with task prefixes removed, when most lines carry one; else None."""
    lines = [line for line in text.split("\n") if line.strip()]
    prefixed = sum(1 for line in lines if _TASK_PREFIX.match(line))
    if not lines or prefixed * 2 < len(lines):
        return None
    return _TASK_PREFIX.sub("", text)
