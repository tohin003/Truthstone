"""Day 3: existing tests rewritten for behaviour the request did not ask for (``original_tests_fail``).

At a completion claim, existing tests the task changed beyond pure additions get their original
text back in a sandboxed copy of the tree and run there with the session's own runner. An
original test that fails with an assertion failure, for inputs the request never mentions,
speaks. A requested behaviour change (the request names the input), a cleanup whose original
test no longer loads, a run past the time budget, a machine without a sandbox and pure test
additions are silent. Made-up repositories only.
"""

from __future__ import annotations

import shutil
import sys
import time

import pytest

from tests.test_audit_stop_kit import CodexSession, assert_silent, make_repo, npm_wrap, pytest_output
from truthstone.core.config import ChallengeSettings, Settings
from truthstone.core.engine import Guard
from truthstone.validate import original_tests as ot

needs_sandbox = pytest.mark.skipif(not ot.sandbox_available(), reason="needs macOS sandbox-exec")

SLUG = '''import re


def title_slug(text: str) -> str:
    """Lowercase words of letters and digits, joined by hyphens."""
    return "-".join(re.findall(r"[a-z0-9]+", text.lower()))
'''
# The change asked for (letters and digits apart) also splits "7b", which the request never mentions.
SPLIT = SLUG.replace('r"[a-z0-9]+"', 'r"[a-z]+|[0-9]+"')
TESTS = '''from quill.slug import title_slug


def test_plain_words():
    assert title_slug("Paper Lantern") == "paper-lantern"


def test_digits_stay_with_their_word():
    assert title_slug("Room 7b Notes") == "room-7b-notes"
'''
REWRITTEN = TESTS.replace('"room-7b-notes"', '"room-7-b-notes"')
ADDED = TESTS + '''

def test_letters_and_digits_apart():
    assert title_slug("Mix9Up") == "mix-9-up"
'''
LEGACY = 'def old_slug(text: str) -> str:\n    return text.lower().replace(" ", "_")\n'
LEGACY_TESTS = (
    'from quill.legacy import old_slug\n\n\ndef test_old_slug():\n    assert old_slug("A B") == "a_b"\n'
)
FILES = {
    "pyproject.toml": (
        '[project]\nname = "quill"\nversion = "0.1.0"\n\n[tool.pytest.ini_options]\npythonpath = ["src"]\n'
    ),
    "src/quill/__init__.py": "",
    "src/quill/slug.py": SLUG,
    "src/quill/legacy.py": LEGACY,
    "tests/test_slug.py": TESTS,
    "tests/test_legacy.py": LEGACY_TESTS,
    "README.md": "# quill\n\nSlugs for page titles.\n",
}
PYTEST = f"{sys.executable} -m pytest -q"
ASKED = 'Please make title_slug split letters from digits: `title_slug("Mix9Up")` should give "mix-9-up".'
DONE = "title_slug now splits letters from digits. `pytest -q`: all tests pass.\n\nFINAL: done"


class OptedIn(CodexSession):
    """A Codex-shaped session with ``[challenge] original_tests = true`` (the check is opt-in)."""

    def __init__(self, repo, enabled: bool = True) -> None:
        super().__init__(repo)
        self.guard.close()
        self.guard = Guard(Settings(profile="minimal", challenge=ChallengeSettings(original_tests=enabled)))
        self.guard.workspace(repo).index.ready(timeout=30)


@pytest.fixture
def session(tmp_path):
    made: list[CodexSession] = []

    def make(files: dict[str, str] = FILES, enabled: bool = True) -> CodexSession:
        made.append(OptedIn(make_repo(tmp_path / f"quill{len(made)}", files), enabled))
        return made[-1]

    yield make
    for each in made:
        each.close()


def _change(session: CodexSession, prompt: str, tests: str) -> dict:
    session.prompt(prompt)
    session.run(PYTEST, pytest_output([], 3))
    session.write("src/quill/slug.py", SPLIT)
    session.write("tests/test_slug.py", tests)
    session.run(PYTEST, pytest_output([], 3))
    return session.stop(DONE)


@needs_sandbox
def test_an_existing_expectation_rewritten_for_an_input_the_request_never_mentions_speaks(session):
    out = _change(session(), ASKED, REWRITTEN)
    assert out.get("decision") == "block"
    reason = out["reason"]
    assert "Tests that existed before this task fail on your final code as they were written" in reason
    assert "tests/test_slug.py: test_digits_stay_with_their_word" in reason
    assert "fails with: AssertionError: assert 'room-7-b-notes' == 'room-7b-notes'" in reason
    assert 'it checks "Room 7b Notes" and the request mentions none of them' in reason
    assert "restore the old behaviour for the inputs the request did not name" in reason
    assert "make the tests pass" not in reason.lower()


@needs_sandbox
def test_a_requested_change_whose_input_the_request_names_is_silent(session):
    asked = 'Make title_slug split letters from digits: `title_slug("Room 7b Notes")` is "room-7-b-notes".'
    one = session()
    assert_silent(one, _change(one, asked, REWRITTEN))


@needs_sandbox
def test_a_cleanup_whose_original_test_no_longer_loads_is_silent(session):
    one = session()
    one.prompt("Remove the deprecated `quill/legacy.py` module and its test file; nothing uses it any more.")
    one.run(PYTEST, pytest_output([], 3))
    one.delete("src/quill/legacy.py")
    one.delete("tests/test_legacy.py")
    one.run(PYTEST, pytest_output([], 2))
    done = "Removed the legacy module and its tests. `pytest -q`: 2 passed.\n\nFINAL: done"
    assert_silent(one, one.stop(done))


@needs_sandbox
def test_a_run_past_the_budget_is_killed_and_silent(session, tmp_path):
    woke = tmp_path / "woke"
    slow = TESTS.replace(
        "def test_digits_stay_with_their_word():\n",
        "def test_digits_stay_with_their_word():\n"
        f"    import time\n    time.sleep(6)\n    open({str(woke)!r}, 'w').write('x')\n",
    )
    one = session({**FILES, "tests/test_slug.py": slow})
    started = time.monotonic()
    out = _change(one, ASKED, slow.replace('"room-7b-notes"', '"room-7-b-notes"'))
    assert_silent(one, out)
    assert time.monotonic() - started < 20
    time.sleep(7)
    assert not woke.exists(), "the timed-out run kept going: its process group was not killed"


def test_off_by_default(session, monkeypatch):
    def never(*_args, **_kwargs):
        raise AssertionError("the original tests were run with the check off")

    monkeypatch.setattr(ot, "_failing_originals", never)
    assert ChallengeSettings().original_tests is False
    one = session(enabled=False)
    assert_silent(one, _change(one, ASKED, REWRITTEN))


def test_without_a_sandbox_the_check_is_silent(session, monkeypatch):
    monkeypatch.setattr(ot, "SANDBOX_EXEC", "/nonexistent/sandbox-exec")
    assert not ot.sandbox_available()
    one = session()
    assert_silent(one, _change(one, ASKED, REWRITTEN))


def test_the_sandbox_is_macos_only(monkeypatch):
    monkeypatch.setattr(ot.sys, "platform", "linux")
    assert not ot.sandbox_available()


def test_pure_test_additions_are_silent_and_run_nothing(session, monkeypatch):
    def never(*_args, **_kwargs):
        raise AssertionError("the original tests were run for pure additions")

    monkeypatch.setattr(ot, "_failing_originals", never)
    one = session()
    assert_silent(one, _change(one, ASKED, ADDED))


def test_no_completion_claim_runs_nothing(session, monkeypatch):
    def never(*_args, **_kwargs):
        raise AssertionError("the original tests were run without a completion claim")

    monkeypatch.setattr(ot, "_failing_originals", never)
    one = session()
    one.prompt(ASKED)
    one.run(PYTEST, pytest_output([], 3))
    one.write("src/quill/slug.py", SPLIT)
    one.write("tests/test_slug.py", REWRITTEN)
    assert_silent(one, one.stop("not done: the slug change also splits mixed tokens; please confirm."))


CASES = "Paper Lantern|paper-lantern\nRoom 7b Notes|room-7b-notes\n"
CASE_TESTS = """from pathlib import Path

from quill.slug import title_slug


def test_every_listed_title():
    for line in (Path(__file__).parent / "cases.txt").read_text().splitlines():
        title, slug = line.split("|")
        assert title_slug(title) == slug
"""


@needs_sandbox
def test_test_data_rewritten_to_match_counts_like_a_rewritten_test(session):
    one = session({**FILES, "tests/cases.txt": CASES, "tests/test_cases.py": CASE_TESTS})
    one.prompt(ASKED)
    one.run(PYTEST, pytest_output([], 4))
    one.write("src/quill/slug.py", SPLIT)
    one.write("tests/test_slug.py", REWRITTEN)
    one.write("tests/cases.txt", CASES.replace("|room-7b-notes", "|room-7-b-notes"))
    one.run(PYTEST, pytest_output([], 4))
    out = one.stop(DONE)
    assert out.get("decision") == "block"
    assert "tests/test_cases.py: test_every_listed_title" in out["reason"]


# -- the same over node:test, through the package's own test script ----------------------------------------

LABEL = 'export function label(name: string): string {\n  return `[${name}]`;\n}\n'
UPPER = 'export function label(name: string): string {\n  return `[${name.toUpperCase()}]`;\n}\n'
SPEC = """import { test } from "node:test";
import assert from "node:assert/strict";
import { label } from "../src/label.ts";

test("labels wrap the name", () => {
  assert.equal(label("lamp"), "[lamp]");
});
"""
TS_FILES = {
    "package.json": (
        '{"name": "tagline", "version": "1.0.0", "type": "module", "scripts": {"test": "node --test"}}\n'
    ),
    "src/label.ts": LABEL,
    "test/label.test.ts": SPEC,
}


@needs_sandbox
@pytest.mark.skipif(shutil.which("node") is None, reason="needs node")
def test_node_test_originals_are_run_with_the_package_test_script(session):
    one = session(TS_FILES)
    one.prompt('Labels should shout: `label("door")` must give "[DOOR]".')
    green = npm_wrap("tagline", "node --test", "ℹ tests 1\nℹ pass 1\nℹ fail 0\n")  # noqa: RUF001 - node glyph
    one.run("npm test", green)
    one.write("src/label.ts", UPPER)
    one.write("test/label.test.ts", SPEC.replace('"[lamp]"', '"[LAMP]"'))
    one.run("npm test", green)
    out = one.stop("Labels now shout. `npm test`: 1 passed.\n\nFINAL: done")
    assert out.get("decision") == "block"
    assert "test/label.test.ts: labels wrap the name" in out["reason"]
    assert 'it checks "lamp" and the request mentions none of them' in out["reason"]


# -- the pieces ------------------------------------------------------------------------------------------


def test_request_examples_and_mentions():
    examples = ot.request_examples('Make `pad_left("ab", 4)` give "  ab"; keep MAX_WIDTH at 120.')
    assert {"pad_left", "ab", "MAX_WIDTH", "120"} <= examples
    assert ot.mentioned("ab", examples) in ("ab", 'pad_left("ab", 4)')
    assert ot.mentioned("pad_left", {"pad_left(x)"}) == "pad_left(x)"  # inside an example
    assert ot.mentioned("value: pad_left x", {"pad_left"}) == "pad_left"  # an example inside a value
    assert ot.mentioned("padded", {"pad"}) is None  # not at a token boundary
    assert ot.request_examples("Tidy up the module, please.") == set()
