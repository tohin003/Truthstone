"""Rebuild a task's working state from the store (R14).

`TaskState` lives in the engine's memory. A daemon restart mid-task, or an eviction from
the live-task window, forgot it, and Stop after failing tests returned allow (D3 reproduced
it three ways). The store has what is needed: the task as it was opened, its post-tool
events and its test runs (`ProjectStore.task_record`, `task_activity`). This replays them,
in the order the daemon handled them, into a fresh `TaskState`: each change and each run
takes the next place on the timeline, so G2a's "latest run decides" and "changed after the
pass" read the rebuilt task exactly as they read the live one.

What the store does not hold stays as a fresh task has it: changes made through shell
commands (a sweep attributes them; no event names their paths), the tests that covered a
deleted file, the files the task created, parse baselines, runs whose result could not be
read, and how often the gate has spoken.

Verification rows are read field by field, each with a fallback: older rows hold only
``command``, ``summary`` and ``failed``. The row's status is authoritative for the outcome;
the suite (``family``, ``key``, ``scope``) is derived from the command when it is missing,
by the same function the live path uses (`verify.commands.test_invocation`).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

from truthstone import complexity, intent
from truthstone.core.enums import EventType
from truthstone.core.events import DELETE_TOOLS, MUTATING_TOOLS
from truthstone.core.taskstate import TaskState
from truthstone.intent.models import TaskSpec
from truthstone.repo.index import RepoIndex
from truthstone.verify import commands
from truthstone.verify.runners import TestOutcome

log = logging.getLogger(__name__)

_SUCCESS = str(EventType.POST_TOOL_USE)


def rebuild(
    store: Any, index: RepoIndex, record: dict[str, Any], path_keys: Iterable[str]
) -> tuple[TaskState, dict[str, int]]:
    """A `TaskState` for the stored task ``record``, and what was replayed into it.

    ``path_keys`` are the argument names that hold a changed file's path. Never raises
    for bad rows: a row that cannot be read is skipped.
    """
    task_id = str(record.get("task_id") or "")
    state = TaskState(
        task_id=task_id,
        spec=_spec(record, index),
        session_id=str(record.get("session_id") or ""),
    )
    created = record.get("created_at")
    if isinstance(created, int | float) and not isinstance(created, bool):
        state.started_at = float(created)

    activity = store.task_activity(
        task_id,
        tuple(path_keys),
        change_tools=MUTATING_TOOLS | DELETE_TOOLS,
        removal_tools=DELETE_TOOLS,
    )
    replayed = {"changes": 0, "runs": 0, "truncated": int(bool(activity.get("truncated")))}
    changes, runs = activity.get("changes") or [], activity.get("verifications") or []
    for entry in activity.get("timeline") or []:
        try:
            if entry["kind"] == "change":
                replayed["changes"] += _replay_change(state, index, changes[entry["index"]])
            elif entry["kind"] == "verification":
                replayed["runs"] += _replay_run(state, runs[entry["index"]])
        except Exception:  # one unreadable row never costs the rest of the task
            log.debug("truthstone: skipped an unreadable row rebuilding %s", task_id, exc_info=True)
    return state, replayed


def _spec(record: dict[str, Any], index: RepoIndex) -> TaskSpec:
    """The stored spec when it is whole; otherwise derived again from the prompt."""
    if record.get("depth") == "implicit":
        return TaskSpec.implicit()
    stored = record.get("spec")
    if record.get("spec_complete") and isinstance(stored, dict) and stored:
        try:
            return TaskSpec.model_validate({k: v for k, v in stored.items() if k in TaskSpec.model_fields})
        except Exception:  # a spec written by another version: derive it again
            log.debug("truthstone: stored spec unreadable; re-deriving it", exc_info=True)
    built = index if index.is_built else None
    spec = intent.extract(str(record.get("prompt") or ""), built)
    try:
        spec.complexity = complexity.assess(spec, built)
    except Exception:  # the depth is advisory; the default is "direct"
        log.debug("truthstone: could not re-assess a rebuilt task's complexity", exc_info=True)
    return spec


def _replay_change(state: TaskState, index: RepoIndex, change: dict[str, Any]) -> int:
    if change.get("type") != _SUCCESS:
        return 0  # a failed edit changed nothing (H3)
    path = index.normalize(str(change.get("path") or ""))
    if not path:
        return 0
    if change.get("removed"):
        state.delete(path, set())  # the coverage it had is gone with the old index
    else:
        state.touch(path)
    return 1


def _replay_run(state: TaskState, run: dict[str, Any]) -> int:
    outcome = outcome_from_row(run)
    outcome.seq = state.next_seq()
    if outcome.command:
        state.verification.commands_seen.append(outcome.command)
    if outcome.passed is None:
        state.verification.inconclusive.append(outcome)
    else:
        state.verification.outcomes.append(outcome)
    return 1


def outcome_from_row(run: dict[str, Any]) -> TestOutcome:
    """A stored verification row as the `TestOutcome` the live path recorded."""
    detail = run.get("detail") if isinstance(run.get("detail"), dict) else {}
    status = run.get("status")
    passed = True if status == "passed" else False if status == "failed" else None
    command = _text(detail.get("command"))[:200]
    invocation = commands.test_invocation(command) if command else None
    scope = detail.get("scope")
    failing = detail.get("failing_files")
    return TestOutcome(
        runner=_text(detail.get("runner"))
        or _text(run.get("kind"))
        or (invocation.runner if invocation else "unknown"),
        passed=passed,
        total=_count(detail.get("total")),
        failed=_count(detail.get("failed")),
        summary=_text(detail.get("summary")),
        command=command,
        exit_code=detail.get("exit_code") if _is_int(detail.get("exit_code")) else None,
        family=_text(detail.get("family")) or (invocation.family if invocation else ""),
        key=_text(detail.get("key")) or (invocation.key if invocation else ""),
        scope=(
            tuple(str(item) for item in scope)
            if isinstance(scope, list)
            else (invocation.selectors if invocation else ())
        ),
        failing_files=tuple(str(item) for item in failing) if isinstance(failing, list) else (),
    )


def _text(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _count(value: Any) -> int:
    return max(0, value) if _is_int(value) else 0
