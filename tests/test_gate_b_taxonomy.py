"""C1-taxonomy: the census says exactly what each completion-gate observation proves.

The gate files its findings under three SPEC §3 modes (and one not-a-failure). The
taxonomy's `detector`/`proves` text described the gate as it was before G2a-G15 ("failing
tests or unparsable files", "none were run"), which no longer says what a stale or
narrower run, an in-flight run or an honest hand-back establishes. `GATE_SUBJECTS` is now
the table a reader checks a subject against, and this test keeps it in step with the gate:
every subject the gate can record is explained, under the mode the gate files it.
"""

from __future__ import annotations

import ast
from pathlib import Path

from agentguard.census import render_detectors
from agentguard.census.taxonomy import BY_MODE, GATE_SUBJECTS, TAXONOMY
from agentguard.core.enums import FailureMode
from agentguard.verify import completion_gate

GATE_SOURCE = Path(completion_gate.__file__)


def _is_failure_mode(node: ast.expr) -> bool:
    if not isinstance(node, ast.Attribute):
        return False
    return isinstance(node.value, ast.Name) and node.value.id == "FailureMode"


def _recorded_subjects() -> dict[str, set[FailureMode]]:
    """Every literal ``subject=`` in the gate, with the mode the same call files it under."""
    found: dict[str, set[FailureMode]] = {}
    for node in ast.walk(ast.parse(GATE_SOURCE.read_text(encoding="utf-8"))):
        if not isinstance(node, ast.Call):
            continue
        literals = {
            kw.arg: kw.value.value
            for kw in node.keywords
            if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str)
        }
        subject = literals.get("subject")
        if subject is None:
            continue
        candidates = [*node.args, *(kw.value for kw in node.keywords if kw.arg == "failure_mode")]
        modes = [arg for arg in candidates if _is_failure_mode(arg)]
        assert modes, f"subject {subject!r} is recorded without a literal FailureMode"
        found.setdefault(subject, set()).update(FailureMode[mode.attr] for mode in modes)
    return found


def test_every_gate_subject_is_explained_under_its_mode():
    recorded = _recorded_subjects()
    assert recorded, "the scan found no subjects: it is reading the wrong file"
    for subject, modes in recorded.items():
        assert subject in GATE_SUBJECTS, f"{subject!r} has no entry in GATE_SUBJECTS"
        assert modes == {GATE_SUBJECTS[subject][0]}, subject
        assert GATE_SUBJECTS[subject][1], subject


def test_no_entry_describes_a_subject_the_gate_no_longer_records():
    assert set(GATE_SUBJECTS) == set(_recorded_subjects())


def test_each_counted_subject_is_named_in_its_modes_detector_text():
    """So `agentguard census -v` names the observations behind every number."""
    spec_modes = {entry.mode for entry in TAXONOMY}
    for subject, (mode, _) in GATE_SUBJECTS.items():
        if mode in spec_modes:
            assert f"`{subject}`" in BY_MODE[mode].detector, (subject, mode)
        else:  # not a failure: never counted, but the census still says it exists
            assert mode is FailureMode.NOT_A_FAILURE
            assert any(f"`{subject}`" in entry.proves for entry in TAXONOMY), subject


def test_the_detector_notes_say_what_is_not_proved():
    text = render_detectors()
    for phrase in (
        "It says nothing about the quality of tests that were written",  # pinned by test_s03 too
        "It does NOT prove the agent claimed success in words",
        "It does NOT prove the change is wrong",
        "never counted",
    ):
        assert phrase in text, phrase
