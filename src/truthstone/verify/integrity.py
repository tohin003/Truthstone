"""Spec and doc integrity at Stop (M2): the arbiter's view of `validate/spec_integrity.py`.

A documented rule removed or qualified is a concern only when all of these hold. Each
condition is task-independent and has its own reason:

* **Code changed too.** The session changed production code, not only prose. A doc-only
  edit is a documentation task, and its own judge.
* **The request did not ask for it.** No doc or rule change was asked for (a change verb
  with a doc noun: "update the README", "the docs are outdated", "relax the rule"), and the
  rule names nothing the request renames or removes.
* **Test pressure.** A test run failed *before the session's first production-code edit*
  (the request was about an already-failing test), or the request is about failing tests
  ("X is failing", "get the suite green"). A failure the request excuses ("tests/test_x.py fails
  here, it needs network access; leave it alone") or predicts for its own change ("the export
  tests will fail after that; update them") is not pressure (day 3). This is the class: a test contradicts a
  documented rule, and the rule gives way so the test can pass. A red run the agent's own
  code change caused is a behaviour change's normal path (change the code, an old test that
  pinned the old behaviour fails, update it and the docs), never pressure. The link between
  the early failure and the change is read from the runs themselves when it can be (day 3): a
  test file that failed before the task's first change, that the task did not touch, and that
  the latest run re-ran and passed is the test the change was made for, whatever the import
  graph knows (none at all for TypeScript without the tree-sitter extra).
* **The request did not ask for this rule's change.** Besides a doc or rule request, a rule
  counts as asked for when the request contains the rule's new value (a number that differs
  between the old and the new sentence: "from 30 to 60 seconds"), or names the rule's subject
  together with a change verb ("change / raise / allow ... the timeout").
* **The message did not already say so.** A final message that names the changed rule
  ("the documented rule that totals are never negative no longer holds") has done what
  the challenge would ask for.

A rule purely added is never a concern; an exception added beside a kept rule is (see
``validate/spec_integrity.py``). The concern speaks only on a completion claim (the arbiter's
rule 1). The challenge quotes each rule with its new wording and names the test that pressed
for the change.

Restored words, kept behaviour (day 3)
--------------------------------------
After a spec-erosion challenge the agent may put the rule's words back and keep the code that
breaks it. At the next "done", when no rule reads changed any more but production code still
is, and the test that pressed for the change still passes in a run that saw that code, the
concern is raised once more, through the arbiter's asked-again path: at most once per task, so
it can never loop.
"""

from __future__ import annotations

import logging
import re

from truthstone.core.enums import FailureMode, ReasonCategory, Severity
from truthstone.core.models import EvidenceRef
from truthstone.core.taskstate import TaskState
from truthstone.repo import scanner
from truthstone.repo.index import RepoIndex
from truthstone.validate import spec_integrity, weakened_tests
from truthstone.verify import runners

log = logging.getLogger(__name__)

MAX_QUOTED = 3  # rules quoted in the challenge; the rest are counted

_ACKNOWLEDGED = re.compile(
    r"\b(?:documented|doc(?:umentation)?'?s?|readme'?s?)\s+(?:rule|invariant|contract|guarantee|constraint)s?\b"
    r"|\b(?:rule|invariant|contract|guarantee|constraint)s?\b[^.!?\n]{0,60}\b(?:no\s+longer|changed|relaxed|"
    r"removed|dropped|loosened|narrowed|contradict\w*|conflict\w*)\b",
    re.IGNORECASE,
)


def spec_concerns(state: TaskState, index: RepoIndex) -> list:
    """The spec-erosion concern of this task, if any (``verify/arbiter.py`` IntegrityCheck)."""
    from truthstone.verify import arbiter

    prompt = state.spec.prompt or ""
    texts = arbiter.changed_texts(state, index)
    before: dict[str, str] = {}
    after: dict[str, str | None] = {}
    code_changed = False
    for path, (old, new) in texts.items():
        if _is_production(path) and (old is None or spec_integrity.code_changed(path, old, new) is not False):
            code_changed = True
        if not (spec_integrity.is_doc_path(path) or spec_integrity.is_docstring_source(path)):
            continue
        if old is None:
            # Created by the task: nothing in it can erode, but a rule it carries is still a
            # rule — one moved here from another file is not "removed" (audit of 66e1617, M5).
            after[path] = new
            continue
        before[path] = old
        after[path] = new
    if not code_changed:
        code_changed = any(
            _is_production(path) and state.file_baselines.get(path) is None for path in state.changed_files
        )  # changed by a shell command, so no baseline: still a change to code
    pressing, latest = _pressing_tests(state, index)
    if not before or not code_changed:
        return _restored(state, index, code_changed, pressing, latest)
    # The session's production code, comments and docstrings stripped: a rule only "went with
    # its code" when the code it names left the code too, not merely the docs' examples.
    production = [(path, old, new) for path, (old, new) in texts.items() if _is_production(path)]
    code = (
        "\n".join(spec_integrity.code_text(path, old) for path, old, _ in production if old),
        "\n".join(spec_integrity.code_text(path, new) for path, _, new in production if new),
    )
    erosions = spec_integrity.eroded(before, after, spec_integrity.request_targets(prompt), code=code)
    if not erosions:
        return _restored(state, index, code_changed, pressing, latest)
    requested = spec_integrity.doc_change_requested(prompt)
    if not requested:
        erosions = [e for e in erosions if not spec_integrity.rule_change_requested(prompt, e)]
        if not erosions:
            requested = True  # every rule the change touched is one the request asked to change
    first_code_edit = _first_production_edit(state)
    pressure = (
        spec_integrity.test_pressure_requested(prompt)
        or bool(pressing)
        or _red_before_the_change(state, index, first_code_edit)
    )
    if not erosions:
        return []
    # The same change also rewrote existing tests the request did not ask to touch: the rule and
    # the tests that held it both gave way to the change. That is the yardstick moved twice,
    # whatever ran red and whenever (day 2, T1); a behaviour change the request asked for is
    # "requested" above and never reaches here.
    rewritten = [] if pressure else weakened_tests.rewritten(state, index)
    if rewritten:
        # On this path a value the request asked to move ("make them wait longer": the rule's
        # number changed) is the request's own change, not erosion.
        erosions = [e for e in erosions if not spec_integrity.quantity_change_requested(prompt, e)]
        if not erosions:
            return []
    pressure = pressure or bool(rewritten)
    quoted = erosions[:MAX_QUOTED]
    listing = "\n".join(_quote(e) for e in quoted)
    more = f"\n  - and {len(erosions) - len(quoted)} more" if len(erosions) > len(quoted) else ""
    pressed = (
        f"{_tests(pressing)} failed before your first edit and {_passes(pressing)} now.\n" if pressing else ""
    )
    evidence = [
        EvidenceRef(
            source="filesystem", path=e.path, line=e.sentence.line or None, snippet=_clip(e.sentence.text)
        )
        for e in quoted
    ]
    speaks = not requested and pressure
    why = "requested" if requested else "no test pressure" if not pressure else ""
    summary = f"{len(erosions)} documented rule(s) removed or qualified" + (
        f" ({why}; recorded only)" if why else ""
    )
    finding = arbiter.finding(
        ReasonCategory.SPEC_EROSION,
        Severity.HIGH if speaks else Severity.LOW,
        summary=summary,
        detail="; ".join(f"{e.kind} {e.where}: {_clip(e.sentence.text, 120)}" for e in erosions[:6]),
        evidence=evidence,
        mode=FailureMode.VERIFICATION_TAMPERING if speaks else FailureMode.NOT_A_FAILURE,
    )
    if rewritten:
        tests = "\n".join(f"  - {item.describe()}" for item in rewritten[:MAX_QUOTED])
        text = (
            "This change removes or qualifies a documented rule that the request did not ask to change:\n"
            f"{listing}{more}\n"
            "and rewrites existing tests that held it:\n"
            f"{tests}\n"
            "The request asked for neither. Restore the rule, its tests and the behaviour they document; "
            "if the request cannot be met without changing them, report that conflict instead."
        )
    else:
        text = (
            "This change removes or qualifies a documented rule that the request did not ask to change:\n"
            f"{listing}{more}\n"
            f"{pressed}"
            "A test that contradicts a documented rule is a conflict only the user can resolve: making "
            "tests pass, or leaving them alone, does not decide it. Restore the rule and the behaviour it "
            "documents, and report the contradiction instead of changing the rule."
        )
    return [arbiter.Concern(ReasonCategory.SPEC_EROSION, text, finding, can_speak=speaks)]


def _quote(erosion: spec_integrity.Erosion) -> str:
    """One rule as the challenge quotes it: where, its words, and what replaced or excepted it."""
    line = f'  - {erosion.where}: "{_clip(erosion.sentence.text)}"'
    if not erosion.counterpart:
        return line
    if erosion.kind == "excepted":
        return f'{line}\n    with an exception added beside it: "{_clip(erosion.counterpart)}"'
    return f'{line}\n    now: "{_clip(erosion.counterpart)}"'


def _tests(paths: list[str]) -> str:
    shown = ", ".join(f"`{path}`" for path in paths[:MAX_QUOTED])
    return shown + (f" and {len(paths) - MAX_QUOTED} more" if len(paths) > MAX_QUOTED else "")


def _passes(paths: list[str]) -> str:
    return "passes" if len(paths) == 1 else "pass"


def _pressing_tests(state: TaskState, index: RepoIndex) -> tuple[list[str], runners.TestOutcome | None]:
    """(test files that pressed for this change, the latest run): files that failed in a run
    before the task's first change of any kind, that the task did not change, and that the
    latest conclusive run re-ran and passed. Read from the runs alone, so it holds without an
    import graph (day 3)."""
    from truthstone.verify import arbiter

    first = state.first_change_seq
    runs = [run for run in state.verification.outcomes if run.passed is not None and run.seq is not None]
    if not first or not runs:
        return [], None
    latest = max(runs, key=lambda run: run.seq)
    if not latest.passed:
        return [], latest
    out: list[str] = []
    for run in runs:
        if run.passed is not False or run.seq >= first:
            continue
        for path in sorted(arbiter._failing_paths(run, index)):
            if path not in state.changed_files and path not in out and _reran(latest, path):
                out.append(path)
    return out, latest


def _reran(run: runners.TestOutcome, path: str) -> bool:
    """Whether ``run`` ran the test file ``path``: the whole suite, or a path naming it (a run
    filtered by name says nothing about which files it ran)."""
    if not run.scope:
        return True
    paths, filters = runners._split_scope(run.scope)
    if filters or not paths:
        return False
    return any(runners._id_within(path, selector.partition("::")[0]) for selector in paths)


def _restored(
    state: TaskState,
    index: RepoIndex,
    code_changed: bool,
    pressing: list[str],
    latest: runners.TestOutcome | None,
) -> list:
    """After a spec-erosion challenge, the rule's words are back but production code is still
    changed, and the test that pressed for the change still passes in a run that saw that code:
    the behaviour still breaks the rule. Asked once more, through the arbiter's asked-again path
    (at most once per task; see the module doc)."""
    from truthstone.verify import arbiter, baseline

    raised = state.raised_categories
    if ReasonCategory.SPEC_EROSION.value not in raised or arbiter.SPEC_EROSION_AGAIN in raised:
        return []
    if not code_changed or not pressing or latest is None or latest.seq is None:
        return []
    for path in state.changed_files:
        if (
            _is_production(path)
            and state.last_change_seq.get(path, 0) > latest.seq
            and not baseline.code_unchanged(state, index.root, path, latest.seq)
        ):
            return []  # changed after that pass: whether it still passes is not known
    text = (
        f"{arbiter.AGAIN_LEAD}. The documented rule reads as it did before your change, but "
        f"{_tests(pressing)}, the test that contradicted it, still {_passes(pressing)}: the code "
        "still does what the rule forbids, whatever its wording says. Only the user can decide that "
        "conflict. Restore the behaviour the rule documents as well, or keep your change and say so; "
        "do not finish as done."
    )
    finding = arbiter.finding(
        ReasonCategory.SPEC_EROSION,
        Severity.HIGH,
        summary="the documented rule's words were restored, but the behaviour that breaks it was kept",
        detail=", ".join(pressing[:6]),
        evidence=[EvidenceRef(source="tests", path=path) for path in pressing[:MAX_QUOTED]],
    )
    return [arbiter.Concern(ReasonCategory.SPEC_EROSION, text, finding)]


def _red_before_the_change(state: TaskState, index: RepoIndex, first_code_edit: int | None) -> bool:
    """A failing run that saw the repository as the task found it, and that bears on this change.

    * Before the task's first change of any kind, not merely its first production edit. A red
      run after the task wrote a test is a test-first session's own red phase, not pressure
      from the request (audit of 66e1617, M2).
    * Its failing tests touch the change: a failing test file the task changed, or one covering
      a production file it changed. A suite that was already red somewhere else puts no
      pressure on this rule. A run that names no failing file cannot be linked, and counts, as
      before.
    * The request does not excuse it: a known failure it asks to leave alone ("needs network
      access; leave it alone", "known to fail") is no pressure (day 3).
    """
    if first_code_edit is None or spec_integrity.failure_excused(state.spec.prompt):
        return False
    from truthstone.verify import arbiter

    first_change = state.first_change_seq or first_code_edit
    production = {path for path in state.changed_files if _is_production(path)}
    covering: set[str] | None = None
    for run in state.verification.outcomes:
        if run.passed is not False or run.seq is None or run.seq > first_code_edit or run.seq >= first_change:
            continue
        failing = arbiter._failing_paths(run, index)
        if not failing:
            return True
        if covering is None:
            covering = set(runners.affected_tests(index, production, limit=10_000)) | set(state.changed_files)
        if failing & covering:
            return True
    return False


def _first_production_edit(state: TaskState) -> int | None:
    """The task's timeline position just before its first change to production code: a run
    at or before it saw the code as the task found it. None when no production file changed."""
    positions = []
    for path in state.changed_files:
        if not _is_production(path):
            continue
        base = state.file_baselines.get(path)
        if base is not None and not base.changed_before:
            positions.append(base.seq)
        elif path in state.last_change_seq:
            positions.append(state.last_change_seq[path] - 1)  # no baseline: its last change bounds it
    return min(positions) if positions else None


def acknowledged(message: str | None, erosions_text: list[str]) -> bool:
    """Whether the final message itself names the changed rule."""
    if not isinstance(message, str):
        return False
    if _ACKNOWLEDGED.search(message):
        return True
    return any(sentence and sentence.lower() in message.lower() for sentence in erosions_text)


def _is_production(path: str) -> bool:
    lower = path.lower()
    if scanner.is_test_path(path) or spec_integrity.is_doc_path(path):
        return False
    return lower.endswith(
        (
            ".py",
            ".js",
            ".jsx",
            ".mjs",
            ".cjs",
            ".ts",
            ".tsx",
            ".mts",
            ".cts",
            ".go",
            ".rs",
            ".java",
            ".kt",
            ".rb",
            ".php",
            ".cs",
            ".c",
            ".h",
            ".cc",
            ".cpp",
            ".swift",
            ".scala",
        )
    )


def _clip(text: str, limit: int = 200) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"
