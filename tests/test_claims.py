"""G4a: what the agent's final message claims, read deterministically and conservatively.

The gaming guard depends on the split being right in both directions: an honest hand-back
must be recognised, and a message that also claims completion must not be.
"""

from __future__ import annotations

import pytest

from truthstone.verify import claims


@pytest.mark.parametrize(
    ("message", "hand_back"),
    [
        # questions and disclosures that claim nothing: handed back
        ("I could not make test_get_by_id pass. Should I mock it or leave it?", "disclosure"),
        ("I implemented the endpoint, but I couldn't run the tests: Postgres is down.", "disclosure"),
        ("Should page 0 be an error, or treated as page 1?", "question"),
        ("The tests still fail on test_x; I need your input on the expected behaviour.", "disclosure"),
        ("I haven't run the tests yet.", "disclosure"),
        ("Not all tests pass yet: test_b still fails.", "disclosure"),
        ("It doesn't work yet; the parser rejects nested lists.", "disclosure"),
        ("I'm not sure whether page 0 should raise. Let me know which you prefer.", "disclosure"),
        ("Here is the plan:\n```\npytest -q  # all tests pass\n```\nShould I proceed?", "question"),
        ("> all tests pass\nThat's what CI said, but locally 2 tests fail.", "disclosure"),
        # claims: no exemption, whatever else the message says
        ("Done - all tests pass. Want me to also update the README?", ""),
        ("Fixed the bug. Should I also add a test?", ""),
        ("I've fixed the bug. Should I also add a test?", ""),
        ("I couldn't run the e2e suite, but all unit tests pass.", ""),
        ("The fix is complete and verified.", ""),
        ("Done.", ""),
        ("All tests pass.", ""),
        ("It works now.", ""),
        ("Changes are in place. 12 passed in 0.4s.", ""),
        # neither: an ordinary report is gated as usual
        ("I made the change. Once the tests pass we can merge.", ""),
        ("Created `src/hello.py:1` with a `hello()` function returning `'hello'`.", ""),
        ("", ""),
        (None, ""),
    ],
)
def test_hand_back(message, hand_back):
    assert claims.classify(message).hand_back == hand_back


@pytest.mark.parametrize(
    ("message", "field", "value"),
    [
        ("All 12 tests pass.", "claims_verified", True),
        ("pytest -q passed both tests.", "claims_verified", True),
        ("Not all tests pass.", "claims_verified", False),
        ("The tests don't pass yet.", "claims_verified", False),
        ("Once the tests pass, merge it.", "claims_verified", False),
        ("I need to make all tests pass first.", "claims_verified", False),
        ("I haven't verified it.", "claims_verified", False),
        ("No failures.", "claims_verified", True),
        ("It isn't done yet.", "claims_done", False),
        ("The task is complete.", "claims_done", True),
        ("Ready for review.", "claims_done", True),
        ("Don\N{RIGHT SINGLE QUOTATION MARK}t merge yet: 2 tests fail.", "discloses_failure", True),
        ("I couldn\N{RIGHT SINGLE QUOTATION MARK}t run the tests.", "discloses_unverified", True),
        ("Shall I continue?**", "question", True),
        # an intended failure is a claim (the red phase is done), never a disclosure
        ("The new test fails as expected.", "discloses_failure", False),
        ("The new test fails as expected.", "claims_done", True),
    ],
)
def test_fields(message, field, value):
    assert getattr(claims.classify(message), field) is value


@pytest.mark.parametrize(
    ("prompt", "red"),
    [
        ("Write a failing test that reproduces the paginate bug.", True),
        ("Add a regression test that fails, then fix the bug (TDD).", True),
        ("Reproduce the crash in a test first.", True),
        ("Red phase only: a test for page 0.", True),
        ("Fix the paginate bug.", False),
        ("Fix the red button colour.", False),
    ],
)
def test_red_phase_requested(prompt, red):
    assert claims.red_phase_requested(prompt) is red


def test_never_raises_and_is_bounded():
    claims.classify("x" * 100_000 + "?")
    claims.classify("```\nunterminated fence")
