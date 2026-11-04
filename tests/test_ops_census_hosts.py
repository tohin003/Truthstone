"""The census is host-aware (H7): a mode is only "never observed" where a host fed its
detector, and a host without a prompt event never has its decisions counted as tasks.

Before: instrumentation was fixed per detector, so a host without a Stop hook reported
false completion as "instrumented, never observed" — the unmeasured zero the census exists
to refuse — and, with no prompt event, every decision counted as a task of its own
(`COUNT(DISTINCT COALESCE(task_id, decision_id))`).
"""

from __future__ import annotations

import re
import shutil
import textwrap
from pathlib import Path

import pytest

from truthstone.census import collect, render
from truthstone.census import report as census_report
from truthstone.census.taxonomy import ALL_MODES, TAXONOMY
from truthstone.core import hosts as core_hosts
from truthstone.core.config import Settings
from truthstone.core.engine import Guard
from truthstone.core.enums import EventType, FailureMode
from truthstone.core.events import AgentEvent
from truthstone.core.store import ProjectStore

FIXTURES = Path(__file__).parent / "fixtures"
HALLUCINATING_FILE = textwrap.dedent(
    """
    from shop.repositories.user import UserRepository

    def report(session):
        return UserRepository(session).get_active_users()
    """
)
GATE_MODES = {FailureMode.FALSE_COMPLETION, FailureMode.INSUFFICIENT_TESTS, FailureMode.UNVERIFIED_CHANGE}
SCOPE_MODES = {FailureMode.UNRELATED_FILES_MODIFIED, FailureMode.OVERPLANNED_TRIVIAL}


@pytest.fixture
def repo(tmp_path) -> Path:
    return Path(shutil.copytree(FIXTURES / "pyrepo", tmp_path / "pyrepo"))


def _event(repo: Path, agent: str, session: str, kind: EventType, tool: str | None = None, **args):
    return AgentEvent(
        event=kind,
        agent=agent,
        workspace=str(repo),
        session_id=session,
        tool=tool,
        arguments=args,
        prompt_text="Add an active-users report." if kind is EventType.USER_PROMPT else None,
    )


def _hallucinating_write(guard: Guard, repo: Path, agent: str, session: str) -> None:
    target = "src/shop/api/report.py"
    write = {"file_path": target, "content": HALLUCINATING_FILE}
    guard.handle(_event(repo, agent, session, EventType.PRE_TOOL_USE, "Write", **write))
    guard.handle(_event(repo, agent, session, EventType.POST_TOOL_USE, "Write", file_path=target))


def _record(repo: Path, claude: bool, cursor: bool) -> None:
    """Claude Code: the full lifecycle. "cursor": a host Truthstone has no profile for,
    sending tool events only — no prompt, no stop."""
    guard = Guard(Settings(observe_only=True))
    guard.workspace(repo).index.ready(timeout=30)
    try:
        if claude:
            guard.handle(_event(repo, "claude-code", "c1", EventType.SESSION_START))
            guard.handle(_event(repo, "claude-code", "c1", EventType.USER_PROMPT))
            _hallucinating_write(guard, repo, "claude-code", "c1")
            guard.handle(_event(repo, "claude-code", "c1", EventType.STOP))
        if cursor:
            _hallucinating_write(guard, repo, "cursor", "x1")
            _hallucinating_write(guard, repo, "cursor", "x1")
    finally:
        guard.close()


def _modes(specs) -> set[FailureMode]:
    return {spec.mode for spec in specs}


def test_census_reports_per_host_instrumentation(repo):
    _record(repo, claude=True, cursor=True)
    census = collect(ProjectStore.for_workspace(repo), days=1)

    hosts = {host.name: host for host in census.hosts}
    assert set(hosts) == {"claude-code", "cursor"}
    claude, cursor = hosts["claude-code"], hosts["cursor"]
    assert (claude.sessions, claude.tasks, claude.opens_tasks) == (1, 1, True)
    assert not claude.blind, "Claude Code feeds every detector"
    assert cursor.sessions == 1 and not cursor.opens_tasks and cursor.profile == "conservative"
    for mode in GATE_MODES:
        assert set(cursor.blind[mode]) == {census_report.TASK, census_report.STOP}
    for mode in SCOPE_MODES:
        assert cursor.blind[mode] == (census_report.TASK,)
    assert cursor.can_observe(FailureMode.HALLUCINATED_API)

    api = next(o for o in census.observed if o.spec.mode is FailureMode.HALLUCINATED_API)
    assert api.by_host == {"claude-code": 1, "cursor": 2}
    assert (api.tasks, api.untasked) == (1, 2), "cursor's decisions are not tasks"
    assert api.denominator == 1

    # Silent where Claude Code could have spoken, and said to be Claude Code's alone.
    silent = _modes(census.silent)
    assert FailureMode.FALSE_COMPLETION in silent
    text = render(census)
    assert re.search(r"claude-code\s+1 session\(s\) · 1 task\(s\)", text)
    assert re.search(r"cursor\s+1 session\(s\) · tasks: — \(it sends no prompt event", text)
    assert "not instrumented on cursor (no prompt event, so no task; no stop event):" in text
    lines = text.splitlines()
    false_completion = next(line for line in lines if "incorrectly claim" in line and "only" in line)
    assert "(on claude-code only)" in false_completion

    payload = census.to_dict()
    by_name = {host["host"]: host for host in payload["hosts"]}
    assert by_name["cursor"]["tasks"] is None and by_name["claude-code"]["tasks"] == 1
    assert {entry["mode"] for entry in by_name["cursor"]["not_instrumented"]} >= {str(m) for m in GATE_MODES}


def test_unknown_host_never_reports_unmeasured_zero(repo):
    _record(repo, claude=False, cursor=True)
    census = collect(ProjectStore.for_workspace(repo), days=1)

    blind = GATE_MODES | SCOPE_MODES
    assert blind <= _modes(census.unobservable), "no host here could feed these detectors"
    assert not blind & _modes(census.silent), "so they are not 'never observed'"
    groups = (census.observed, census.silent, census.unobservable, census.uninstrumented)
    assert sum(len(group) for group in groups) == len(TAXONOMY), "four groups partition §3"

    text = render(census)
    never = text.partition("instrumented, never observed")[2].partition("\n\n")[0]
    assert not any(spec.spec_text in never for spec in ALL_MODES if spec.mode in blind)
    assert "instrumented, but no active host can feed the detector — no number" in text
    blind_texts = {spec.spec_text for spec in ALL_MODES if spec.mode in blind}
    for line in text.splitlines():
        if any(spec_text in line for spec_text in blind_texts):
            assert not re.search(r"\b0\b", line.replace("§3", "")), line
    # No task boundary, no task count: "—", never 0, and no rate.
    row = next(line for line in text.splitlines() if line.strip().startswith("1  hallucinate APIs"))
    assert row.split()[-3:] == ["—", "2", "—"], row
    assert "tasks: —" in text and "0 task(s)" not in text.split("observed\n")[0].split("hosts")[1]

    payload = census.to_dict()
    unobservable = {entry["mode"]: entry for entry in payload["not_instrumented_on_active_hosts"]}
    assert set(unobservable) >= {str(mode) for mode in blind}
    why = unobservable["false_completion"]["hosts"]["cursor"]
    assert why == ["no prompt event, so no task", "no stop event"]
    assert payload["hosts"][0]["tasks"] is None


def test_a_known_profile_declares_what_it_was_not_yet_seen_sending(repo):
    """Codex's profile has a Stop hook; a window with no stop event yet is still one in
    which the gate was listening. An unknown host's assumed profile declares nothing."""
    declared = census_report.declared_events(core_hosts.CODEX)
    assert {census_report.PRE_TOOL, census_report.POST_TOOL, census_report.STOP, "user_prompt"} <= declared
    assert census_report.declared_events(core_hosts.CONSERVATIVE) == set()

    guard = Guard(Settings(observe_only=True))
    guard.workspace(repo).index.ready(timeout=30)
    try:
        guard.handle(_event(repo, "codex", "k1", EventType.USER_PROMPT))
        _hallucinating_write(guard, repo, "codex", "k1")
    finally:
        guard.close()
    census = collect(ProjectStore.for_workspace(repo), days=1)
    (codex,) = census.hosts
    assert codex.profile == "codex" and not codex.blind
    assert FailureMode.FALSE_COMPLETION in _modes(census.silent)


def test_every_instrumented_mode_says_what_its_detector_needs():
    mapped = census_report.DETECTOR_NEEDS
    missing = [spec.mode for spec in ALL_MODES if spec.instrumented and spec.mode not in mapped]
    assert not missing, "map the new detector in census/report.py DETECTOR_NEEDS"


def test_decisions_outside_a_task_are_not_counted_as_tasks(repo):
    _record(repo, claude=False, cursor=True)
    rows = {row["failure_mode"]: row for row in ProjectStore.for_workspace(repo).failure_mode_counts(0)}
    assert rows["hallucinated_api"]["occurrences"] == 2
    assert rows["hallucinated_api"]["tasks"] == 0 and rows["hallucinated_api"]["untasked"] == 2


def test_an_empty_window_still_does_not_claim_to_have_looked(repo):
    census = collect(ProjectStore.for_workspace(repo), days=1)
    assert census.hosts == [] and census.unobservable == []
    assert "instrumented — but there was nothing to observe" in render(census)
