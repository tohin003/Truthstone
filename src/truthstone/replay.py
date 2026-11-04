"""``truthstone replay``: recorded cells through this build's engine, offline (WP1b).

The benchmark's recorder keeps, for every hook event of a cell, the payload exactly as the
host sent it and the tree the working directory held at that moment, with the git objects
to rebuild it (``bench/replay.py`` reads that trace). This module is the core's half: it
feeds those events, in order, through **this build's** engine on exactly the daemon's path
(the host adapter, ``Guard.handle``, the adapter's rendering), and reports what each event
would have produced: the decision, its intervention kind (``core/profile.py``) and what
would have reached the agent.

Each cell runs in a scratch home (its own database, its own config) and a scratch
repository: ``git init``, the session's first tree committed as HEAD (the pristine
checkout the agent started from), then the working tree moved to each event's recorded
tree before the event is handled. The payloads' paths are rewritten from the recorded
working directory to the scratch one. No model is called, nothing leaves the scratch
directories, and the result is deterministic: sweeps of the tree are never rate-limited
during a replay (live, a skipped sweep's changes wait for the next one, so decisions
agree), and the index is built before the first event rather than raced.

Corpus mode joins each cell's graded outcome (``cells.jsonl``, overridden by
``regrade.json`` where the cell was re-graded) and summarises the interventions by kind on
control cells, honest successes and false completions.
"""

from __future__ import annotations

import contextlib
import fnmatch
import json
import os
import shutil
import subprocess
import tempfile
from collections import Counter, defaultdict
from collections.abc import Iterator, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from truthstone.bench import replay as trace
from truthstone.core import profile

ADAPTER = "codex"  # every recorded corpus so far is Codex; the adapter is a parameter
GIT_ENV = {
    "GIT_AUTHOR_NAME": "replay",
    "GIT_AUTHOR_EMAIL": "replay@localhost",
    "GIT_COMMITTER_NAME": "replay",
    "GIT_COMMITTER_EMAIL": "replay@localhost",
}
HONEST = ("pass_claimed", "correct_refusal", "pass_unclaimed")
FALSE_COMPLETION = "false_completion"


# -- one cell ---------------------------------------------------------------------------


@dataclass(slots=True)
class EventResult:
    """What this build does with one recorded host event."""

    index: int
    event: str
    tool: str | None
    action: str  # the decision the host would act on (combined over a multi-file patch)
    would_have: str | None
    kind: str | None  # the intervention kind, for a decision that says (or withheld) something
    reaches: str | None  # deny / block / ask / context: what the agent would perceive, or None
    output: dict[str, Any]
    reason: str = ""
    context: str | None = None
    findings: list[dict[str, Any]] = field(default_factory=list)
    decisions: list[dict[str, Any]] = field(default_factory=list)  # one per core event
    withheld: str | None = None  # the kind the profile recorded instead of saying

    @property
    def intervened(self) -> bool:
        return self.reaches is not None


@dataclass(slots=True)
class CellReplay:
    cell: str
    events: list[EventResult]
    problems: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)  # replayable, with these approximations

    @property
    def interventions(self) -> list[EventResult]:
        return [e for e in self.events if e.intervened]

    def to_json(self) -> dict[str, Any]:
        return {
            "cell": self.cell,
            "problems": self.problems,
            "notes": self.notes,
            "interventions": [_brief(e) for e in self.interventions],
            "withheld": [
                {"index": e.index, "event": e.event, "kind": e.withheld} for e in self.events if e.withheld
            ],
            "events": [asdict(e) for e in self.events],
        }


def _brief(result: EventResult) -> dict[str, Any]:
    return {
        "index": result.index,
        "event": result.event,
        "tool": result.tool,
        "kind": result.kind,
        "reaches": result.reaches,
        "text": (result.reason or result.context or "")[:400],
    }


def reaches(output: dict[str, Any]) -> str | None:
    """What of a host output the agent perceives (``systemMessage`` is the developer's)."""
    from truthstone.adapters.codex import render

    return render.perceived(output)


class ScratchRepo:
    """A git repository whose HEAD is the session's first tree and whose working tree is
    moved to each event's tree; objects are borrowed from the trace (alternates)."""

    def __init__(self, root: Path, objects: Path) -> None:
        self.root = root
        self.current: str | None = None
        root.mkdir(parents=True, exist_ok=True)
        self._env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        self._env.update(GIT_ENV)
        self._git("init", "-q")
        alternates = root / ".git" / "objects" / "info" / "alternates"
        alternates.parent.mkdir(parents=True, exist_ok=True)
        alternates.write_text(str(objects.resolve()) + "\n", encoding="utf-8")

    def _git(self, *argv: str) -> str:
        proc = subprocess.run(
            ["git", "-C", str(self.root), *argv],
            env=self._env,
            capture_output=True,
            text=True,
            timeout=120,
            check=True,
        )
        return proc.stdout.strip()

    def checkout(self, tree: str) -> None:
        if tree == self.current:
            return
        # The index follows the tree; files the old one had and the new one lacks go.
        self._git("read-tree", "--reset", "-u", tree)
        if self.current is None:  # the session's start: commit it as HEAD
            commit = self._git("commit-tree", tree, "-m", "the tree the session started from")
            self._git("update-ref", "HEAD", commit)
        self.current = tree


def _rewrite(value: Any, old: str, new: str) -> Any:
    """``value`` with every occurrence of the recorded working directory moved."""
    if isinstance(value, str):
        return value.replace(old, new) if old in value else value
    if isinstance(value, dict):
        return {k: _rewrite(v, old, new) for k, v in value.items()}
    if isinstance(value, list):
        return [_rewrite(v, old, new) for v in value]
    return value


@contextlib.contextmanager
def scratch_home(home: Path, config: Path | None = None) -> Iterator[Path]:
    """``TRUTHSTONE_HOME`` pointed at ``home`` for the duration, with a fresh database."""
    from truthstone.core.config import ENV_HOME
    from truthstone.core.store import Database

    home.mkdir(parents=True, exist_ok=True, mode=0o700)
    if config is not None:
        shutil.copyfile(config, home / "config.toml")
    saved = {k: os.environ.get(k) for k in (ENV_HOME, "TRUTHSTONE_OBSERVE", "TRUTHSTONE_DISABLE")}
    os.environ[ENV_HOME] = str(home)
    for name in ("TRUTHSTONE_OBSERVE", "TRUTHSTONE_DISABLE"):
        os.environ.pop(name, None)
    Database.reset_shared()
    try:
        yield home
    finally:
        Database.reset_shared()
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


@contextlib.contextmanager
def deterministic_sweeps() -> Iterator[None]:
    """Never rate-limit a sweep while replaying: the result must not depend on how fast
    the replay runs (module docstring)."""
    from truthstone.core import engine

    names = ("BOUNDARY_REFRESH_INTERVAL", "SHELL_SWEEP_INTERVAL", "STOP_SWEEP_INTERVAL")
    saved = {name: getattr(engine, name) for name in names}
    try:
        for name in names:
            setattr(engine, name, 0.0)
        yield
    finally:
        for name, value in saved.items():
            setattr(engine, name, value)


def _dispatch(guard: Any, payload: dict[str, Any], adapter: str) -> tuple[dict, list, Any]:
    """The daemon's path for one payload: (host output, [(event, decision)], decision)."""
    if adapter == "codex":
        from truthstone.adapters.codex import translate

        return translate.dispatch(guard, payload)
    from truthstone.adapters import registry

    impl = registry.get(adapter)
    if impl is None:
        raise ValueError(f"no adapter named {adapter!r}")
    event = impl.to_event(payload)
    if event is None:
        return {}, [], None
    decision = guard.handle(event)
    return impl.from_decision(event, decision, impl.hook_name(payload)), [(event, decision)], decision


def _finding(f: Any) -> dict[str, Any]:
    return {
        "subject": f.subject,
        "category": str(f.category),
        "failure_mode": str(f.failure_mode),
        "severity": str(f.severity),
        "summary": f.summary[:300],
    }


def _result(
    index: int, name: str, tool: str | None, output: dict, results: list, decision: Any
) -> EventResult:
    if decision is None:
        return EventResult(index, name, tool, "allow", None, None, None, output)
    perceived = reaches(output)
    withheld = getattr(decision, "withheld", None)
    says = perceived is not None or decision.would_have is not None or withheld
    return EventResult(
        index=index,
        event=name,
        tool=tool,
        action=str(decision.action),
        would_have=str(decision.would_have) if decision.would_have is not None else None,
        kind=getattr(decision, "kind", None) or (profile.kind_of(decision) if says else None),
        reaches=perceived,
        output=output,
        reason=decision.reason[:2000],
        context=decision.additional_context,
        findings=[_finding(f) for f in decision.findings],
        decisions=[
            {
                "event_type": str(event.event),
                "tool": event.tool,
                "action": str(d.action),
                "would_have": str(d.would_have) if d.would_have is not None else None,
            }
            for event, d in results
        ],
        withheld=withheld or None,
    )


_NO_TREE = "events without a tree"


def infer_trees(events: list[trace.ReplayEvent]) -> tuple[dict[int, str], list[int]]:
    """Each event's tree, filling the few the recorder could not write.

    The recorder misses a tree when two hook calls race for its index lock (parallel tool
    calls). Between two events that saw the same tree, that is the tree. Otherwise a
    PreToolUse takes the tree before it (the state its tool starts from) and anything else
    the tree after it (the state its tool left). Returns the trees and the inferred
    events; an event with neither neighbour has none."""
    trees: dict[int, str] = {}
    inferred: list[int] = []
    for position, event in enumerate(events):
        if event.tree:
            trees[event.index] = event.tree
            continue
        before = next((e.tree for e in reversed(events[:position]) if e.tree), None)
        after = next((e.tree for e in events[position + 1 :] if e.tree), None)
        guess = before if before == after else (before if event.event == "PreToolUse" else after)
        guess = guess or before or after
        if guess:
            trees[event.index] = guess
            inferred.append(event.index)
    return trees, inferred


def replay_cell(
    cell_dir: Path,
    work: Path | None = None,
    config: Path | None = None,
    adapter: str = ADAPTER,
    index_timeout: float = 120.0,
) -> CellReplay:
    """Every recorded event of one cell through this build. Never touches the cell."""
    from truthstone.core.config import Settings
    from truthstone.core.engine import Guard

    corpus = trace.load(cell_dir)
    problems = [p for p in corpus.problems if not p.startswith(_NO_TREE)]
    trees, inferred = infer_trees(corpus.events)
    if len(trees) < len(corpus.events):
        problems.append(f"{_NO_TREE}, and none to infer")
    if problems or not corpus.events:
        return CellReplay(corpus.cell, [], problems or ["no events"])
    notes = [f"trees inferred from neighbouring events (recorder lock races): {inferred}"] if inferred else []
    own = work is None
    work = Path(tempfile.mkdtemp(prefix="truthstone-replay-")) if own else work
    results: list[EventResult] = []
    try:
        repo = ScratchRepo((work / "repo").resolve(), cell_dir / trace.TRACE / "objects")
        with scratch_home(work / "home", config), deterministic_sweeps():
            settings = Settings.load()
            settings.enabled, settings.observe_only = True, False
            guard = Guard(settings)
            try:
                for event in corpus.events:
                    repo.checkout(trees[event.index])
                    if not results:  # the first event: the index is built, not raced
                        guard.workspace(repo.root).index.ready(timeout=index_timeout)
                    recorded_cwd = str(event.payload.get("cwd") or "")
                    payload = _rewrite(event.payload, recorded_cwd, str(repo.root)) if recorded_cwd else dict(
                        event.payload, cwd=str(repo.root)
                    )
                    output, decided, decision = _dispatch(guard, payload, adapter)
                    results.append(_result(event.index, event.event, event.tool, output, decided, decision))
            finally:
                guard.close()
    finally:
        if own:
            shutil.rmtree(work, ignore_errors=True)
    return CellReplay(corpus.cell, results, notes=notes)


# -- a corpus ---------------------------------------------------------------------------


@dataclass(slots=True)
class CellOutcome:
    cell_id: str
    run: str
    cell_dir: Path
    family: str
    recipe: str
    outcome: str
    success: bool | None
    regraded: bool

    @property
    def group(self) -> str:
        """control / honest_success / false_completion / other — the summary's columns."""
        if self.family == "control":
            return "control"
        if self.outcome == FALSE_COMPLETION:
            return "false_completion"
        if self.outcome in HONEST:
            return "honest_success"
        return "other"


def outcomes(run_dir: Path, exclude: Sequence[str] = ()) -> list[CellOutcome]:
    """The valid cells of a run with their graded outcomes (a re-grade wins)."""
    regraded: dict[str, dict[str, Any]] = {}
    path = run_dir / "regrade.json"
    if path.exists():
        regraded = {r["cell_id"]: r for r in json.loads(path.read_text(encoding="utf-8")) if "outcome" in r}
    cells: list[CellOutcome] = []
    for line in (run_dir / "cells.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get("kind") != "cell" or record.get("status") != "valid":
            continue
        cell_id = record["cell_id"]
        if any(fnmatch.fnmatch(cell_id, pattern) or cell_id.startswith(pattern) for pattern in exclude):
            continue
        override = regraded.get(cell_id)
        cells.append(
            CellOutcome(
                cell_id=cell_id,
                run=run_dir.name,
                cell_dir=run_dir / "cells" / cell_id,
                family=str(record.get("family") or ""),
                recipe=str(record.get("recipe") or ""),
                outcome=str((override or record).get("outcome") or ""),
                success=(override or record).get("success"),
                regraded=override is not None,
            )
        )
    return cells


def summarize(rows: list[tuple[CellOutcome, CellReplay]]) -> dict[str, Any]:
    """Interventions by kind, per outcome group: cells reached, events, and examples."""
    groups: dict[str, dict[str, Any]] = {}
    unreplayable = []
    for outcome, replayed in rows:
        if replayed.problems:
            unreplayable.append({"cell": outcome.cell_id, "problems": replayed.problems})
            continue
        group = groups.setdefault(
            outcome.group,
            {"cells": 0, "cells_with_intervention": 0, "by_kind": Counter(), "cells_by_kind": Counter(),
             "withheld_by_kind": Counter(), "examples": defaultdict(list)},
        )
        group["cells"] += 1
        kinds = [f"{e.event}:{e.reaches}:{e.kind}" for e in replayed.interventions]
        if kinds:
            group["cells_with_intervention"] += 1
        group["by_kind"].update(kinds)
        group["cells_by_kind"].update(set(kinds))
        group["withheld_by_kind"].update(f"{e.event}:{e.withheld}" for e in replayed.events if e.withheld)
        for kind in sorted(set(kinds)):
            if len(group["examples"][kind]) < 8:
                group["examples"][kind].append(outcome.cell_id)
    for group in groups.values():
        for key in ("by_kind", "cells_by_kind", "withheld_by_kind"):
            group[key] = dict(sorted(group[key].items()))
        group["examples"] = dict(group["examples"])
    return {"groups": dict(sorted(groups.items())), "unreplayable": unreplayable}


def render(summary: dict[str, Any]) -> str:
    lines: list[str] = []
    for name, group in summary["groups"].items():
        lines.append(
            f"{name}: {group['cells']} cell(s), "
            f"{group['cells_with_intervention']} with a would-have intervention"
        )
        for kind, count in group["by_kind"].items():
            cells = group["cells_by_kind"][kind]
            examples = ", ".join(group["examples"].get(kind, [])[:3])
            lines.append(f"    {kind}: {count} event(s) in {cells} cell(s)  e.g. {examples}")
        for kind, count in group["withheld_by_kind"].items():
            lines.append(f"    (recorded, not shown) {kind}: {count}")
    if summary["unreplayable"]:
        lines.append(f"not replayable: {len(summary['unreplayable'])} cell(s)")
        for item in summary["unreplayable"][:10]:
            lines.append(f"    {item['cell']}: {'; '.join(item['problems'])[:200]}")
    return "\n".join(lines)


def replay_corpus(
    run_dirs: Sequence[Path],
    exclude: Sequence[str] = (),
    config: Path | None = None,
    adapter: str = ADAPTER,
    jobs: int = 1,
) -> list[tuple[CellOutcome, CellReplay]]:
    cells = [cell for run_dir in run_dirs for cell in outcomes(run_dir, exclude)]
    if jobs <= 1:
        return [(cell, replay_cell(cell.cell_dir, config=config, adapter=adapter)) for cell in cells]
    import multiprocessing

    context = multiprocessing.get_context("spawn")  # each worker owns its environment
    with context.Pool(jobs) as pool:
        work = [(str(c.cell_dir), str(config or ""), adapter) for c in cells]
        replayed = pool.starmap(_replay_in_worker, work)
    return list(zip(cells, replayed, strict=True))


def _replay_in_worker(cell_dir: str, config: str, adapter: str) -> CellReplay:
    return replay_cell(Path(cell_dir), config=Path(config) if config else None, adapter=adapter)
