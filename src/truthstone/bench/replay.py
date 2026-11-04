"""Offline replay, the benchmark's half: a recorded cell as an event stream (WP1(b)).

Every cell runs the harness's logging hook (``codex/hook_recorder.py``) in both arms. It
keeps, per hook event, the payload exactly as the host sent it (on PostToolUse that includes
``tool_response``) and the tree the working directory held at that moment, with the git
objects to rebuild it. That makes each cell a deterministic input for any later build: feed
the events, in order, to the build's engine, with the repository checked out at each event's
tree, and compare its would-have decisions with the ones recorded live. No model is called.

This module reads that corpus. ``truthstone replay`` (the product's CLI, owned by the core)
supplies the engine as a ``Decider``; tests plug in their own.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

TRACE = "hooks"  # where the orchestrator keeps a cell's recorder trace


@dataclass(frozen=True, slots=True)
class ReplayEvent:
    index: int
    event: str  # the host's name: SessionStart, UserPromptSubmit, PreToolUse, PostToolUse, Stop...
    ts: float
    payload: dict[str, Any]
    tree: str | None = None
    tree_error: str | None = None
    snapshot: str | None = None  # a Stop's copy of the working tree (stop-<n>)

    @property
    def tool(self) -> str | None:
        return self.payload.get("tool_name")


@dataclass(slots=True)
class Corpus:
    cell: str
    events: list[ReplayEvent]
    problems: list[str] = field(default_factory=list)

    @property
    def replayable(self) -> bool:
        return bool(self.events) and not self.problems


Decider = Callable[[ReplayEvent, Path], dict[str, Any] | None]


def load(cell_dir: Path) -> Corpus:
    """The recorded events of one cell, in order, and what keeps them from replaying."""
    log = cell_dir / TRACE / "hooks.jsonl"
    corpus = Corpus(cell_dir.name, [])
    if not log.exists():
        corpus.problems.append("no recorder trace")
        return corpus
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            record = json.loads(line)
        except ValueError:
            corpus.problems.append("an unreadable trace line")
            continue
        corpus.events.append(
            ReplayEvent(
                index=len(corpus.events),
                event=str(record.get("event") or ""),
                ts=float(record.get("ts") or 0.0),
                payload=record.get("payload") or {},
                tree=record.get("tree"),
                tree_error=record.get("tree_error"),
                snapshot=record.get("snapshot"),
            )
        )
    without_payload = [e.index for e in corpus.events if not e.payload]
    if without_payload:
        corpus.problems.append(f"events without a payload (recorded before WP1): {without_payload[:5]}")
    without_tree = [e.index for e in corpus.events if not e.tree]
    if without_tree:
        corpus.problems.append(f"events without a tree: {without_tree[:5]}")
    if not (cell_dir / TRACE / "objects").is_dir():
        corpus.problems.append("no object store to rebuild trees from")
    return corpus


def checkout(cell_dir: Path, tree: str, dest: Path) -> Path:
    """Rebuild the working tree an event saw into ``dest`` (emptied first)."""
    objects = (cell_dir / TRACE / "objects").resolve()
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix="replay-git-") as scratch:
        clean = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        git_dir = str(Path(scratch) / "git")
        subprocess.run(["git", "init", "-q", "--bare", git_dir], env=clean, check=True, timeout=60)
        env = {
            **clean,
            "GIT_DIR": git_dir,
            "GIT_OBJECT_DIRECTORY": str(objects),
            "GIT_INDEX_FILE": str(Path(scratch) / "index"),
            "GIT_WORK_TREE": str(dest),
        }
        for argv in (["read-tree", tree], ["checkout-index", "--all", "--force"]):
            subprocess.run(["git", *argv], env=env, check=True, capture_output=True, timeout=120)
    return dest


def live_decisions(cell_dir: Path) -> list[dict[str, Any]]:
    """The decisions the guard recorded during the cell, in time order."""
    path = cell_dir / "evidence.json"
    if not path.exists():
        return []
    decisions = json.loads(path.read_text(encoding="utf-8")).get("decisions") or []
    return sorted(decisions, key=lambda d: d.get("ts") or 0)


def replay(cell_dir: Path, decide: Decider, workdir: Path) -> list[dict[str, Any]]:
    """Run every recorded event through ``decide``, the repository checked out at the event's
    tree. Returns one row per event that yielded a decision."""
    corpus = load(cell_dir)
    if not corpus.replayable:
        raise ValueError(f"{corpus.cell} cannot be replayed: {corpus.problems}")
    rows: list[dict[str, Any]] = []
    repo = workdir / "repo"
    current: str | None = None
    for event in corpus.events:
        if event.tree != current:
            checkout(cell_dir, str(event.tree), repo)
            current = event.tree
        decision = decide(event, repo)
        if decision is not None:
            rows.append({"index": event.index, "event": event.event, **decision})
    return rows


def compare(
    live: list[dict[str, Any]],
    replayed: list[dict[str, Any]],
    keys: tuple[str, ...] = ("action", "would_have"),
) -> dict[str, Any]:
    """Live and replayed decisions, paired in order: how many agree on ``keys``."""
    pairs = list(zip(live, replayed, strict=False))
    differ = [
        {"position": i, "live": {k: a.get(k) for k in keys}, "replayed": {k: b.get(k) for k in keys}}
        for i, (a, b) in enumerate(pairs)
        if any(a.get(k) != b.get(k) for k in keys)
    ]
    return {
        "live": len(live),
        "replayed": len(replayed),
        "agree": len(pairs) - len(differ),
        "differ": differ,
        "identical": len(live) == len(replayed) and not differ,
    }


def corpus(run_dir: Path) -> Iterator[Corpus]:
    """Every valid cell of a run that can be replayed."""
    records = {}
    cells_path = run_dir / "cells.jsonl"
    if cells_path.exists():
        for line in cells_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                record = json.loads(line)
                if record.get("kind") == "cell":
                    records[record["cell_id"]] = record
    for cell_dir in sorted((run_dir / "cells").iterdir()):
        if records.get(cell_dir.name, {}).get("status") != "valid":
            continue
        loaded = load(cell_dir)
        if loaded.replayable:
            yield loaded
